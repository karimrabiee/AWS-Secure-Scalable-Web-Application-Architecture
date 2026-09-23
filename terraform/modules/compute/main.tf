# Instances are never reachable directly: no key pairs, no bastion, no
# public IP. The only management path is SSM Session Manager, granted
# through the instance role below.

# Amazon publishes the latest Amazon Linux 2023 AMI ID as a public SSM
# parameter. Reading it here means nobody has to hunt for an AMI ID by
# hand. It is only actually used when var.ami_id is left null (see the
# local below) - once an environment pins an explicit AMI, this data
# source's value is simply ignored.
data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

locals {

  # if var.ami_id is null, use the latest Amazon Linux 2023 AMI; otherwise, use the pinned AMI.
  resolved_ami_id = coalesce(var.ami_id, data.aws_ssm_parameter.al2023.value)
}

data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2_ssm" {
  name               = "${var.name_prefix}-ec2-ssm-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "ec2_ssm_core" {
  role       = aws_iam_role.ec2_ssm.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# this profile is attached to the EC2 instance, granting it the role above (and thus SSM access).
# this works as a "bridge/container" between the instance and the role, since EC2 instances cannot be assigned roles directly.
resource "aws_iam_instance_profile" "ec2_ssm" {
  name = "${var.name_prefix}-ec2-ssm-profile"
  role = aws_iam_role.ec2_ssm.name
}

# this policy grants the EC2 instance permission to read the database secret from Secrets Manager,
#  so it can connect to the RDS instance.
data "aws_iam_policy_document" "read_db_secret" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.db_secret_arn]
  }
}

resource "aws_iam_role_policy" "read_db_secret" {
  name   = "${var.name_prefix}-read-db-secret"
  role   = aws_iam_role.ec2_ssm.id
  policy = data.aws_iam_policy_document.read_db_secret.json
}

resource "aws_launch_template" "app" {
  name          = var.launch_template_name
  image_id      = local.resolved_ami_id
  instance_type = var.instance_type


  iam_instance_profile {
    arn = aws_iam_instance_profile.ec2_ssm.arn
  }

  vpc_security_group_ids = [var.app_sg_id]

  #
  metadata_options {
    #endpoint mode is "enabled" so the instance can reach the IMDSv2 endpoint, but not the legacy IMDSv1.
    http_endpoint = "enabled"
    http_tokens   = "required" # IMDSv2 required for Security
    # hop limit is 1 so the instance cannot use IMDSv2 to reach other instances in the VPC (which would be a security risk).
    http_put_response_hop_limit = 1
  }

  user_data = base64encode(templatefile("${path.module}/user-data.sh.tftpl", {
    app_py_b64       = filebase64("${path.module}/app-src/app.py")
    requirements_b64 = filebase64("${path.module}/app-src/requirements.txt")
    db_secret_arn    = var.db_secret_arn
    db_address       = var.db_address
    db_port          = var.db_port
    db_name          = var.db_name
  }))

  tag_specifications {
    resource_type = "instance"
    tags          = merge(var.tags, { Name = "${var.name_prefix}-app" })
  }

  tags = var.tags

  # NOTE on create_before_destroy: deliberately NOT set here. The launch
  # template uses a fixed name (var.launch_template_name, e.g.
  # "Production-LT"), not a name_prefix-generated one. In normal operation,
  # Terraform updates this resource in place (AMI/instance-type/user-data
  # changes create a new launch template *version*, not a new resource) -
  # but IF some rare change ever forces full replacement, create_before_destroy
  # with a fixed name would try to create a second launch template with the
  # identical name before destroying the first, which AWS rejects. This is
  # the same landmine deliberately avoided on the ASG below - see that
  # resource's comment.
}

resource "aws_autoscaling_group" "app" {
  name                = var.asg_name
  vpc_zone_identifier = var.app_subnet_ids

  min_size         = var.asg_min_size
  desired_capacity = var.asg_desired_capacity
  max_size         = var.asg_max_size

  target_group_arns = [var.target_group_arn]
  health_check_type = "ELB"

  launch_template {
    id      = aws_launch_template.app.id
    version = aws_launch_template.app.latest_version
  }

  # Rolling replacement instead of manual EC2 surgery whenever
  # the launch template changes (new AMI, patched user-data). Checkpoints
  # give a chance to bail out mid-rollout if new instances are unhealthy.
  # No `triggers` list is set: the default behavior (refresh on launch
  # template/version change only) is what's wanted here - explicitly NOT
  # adding "tag" as a trigger, since that would make routine tag edits
  # (e.g. a cost-allocation tag added later) cause a full rolling
  # replacement of the fleet, which the AMI update procedure in
  # docs/OPERATIONS.md does not intend.
  dynamic "instance_refresh" {
    for_each = var.enable_instance_refresh ? [1] : []
    content {
      strategy = "Rolling"
      preferences {
        min_healthy_percentage = 90
        instance_warmup        = 60
      }
    }
  }

  tag {
    key                 = "Name"
    value               = var.asg_name
    propagate_at_launch = true
  }

  dynamic "tag" {
    for_each = var.tags
    content {
      key                 = tag.key
      value               = tag.value
      propagate_at_launch = true
    }
  }

  # NOTE on create_before_destroy: the ASG name is a fixed, explicit value
  # (var.asg_name), not name_prefix-generated. create_before_destroy on a
  # fixed-name resource would collide with itself on any forced replacement
  # (AWS would reject creating a second ASG with the same name before the
  # old one is destroyed). Deliberately omitted here - unlike the launch
  # template and security groups, which use name_prefix specifically so
  # create_before_destroy is safe for them.
}
