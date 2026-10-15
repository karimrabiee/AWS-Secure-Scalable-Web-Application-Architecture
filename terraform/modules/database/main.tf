# Secure database access and disaster recovery. See:
#   docs/OPERATIONS.md   - failover + PITR test scenarios and results
#   docs/DECISIONS.md

resource "aws_db_subnet_group" "main" {
  name       = "${var.name_prefix}-db-subnet-group"
  subnet_ids = var.db_subnet_ids
  tags       = var.tags
}

# Enhanced Monitoring needs its own service role.
data "aws_iam_policy_document" "rds_monitoring_assume" {
  count = var.monitoring_interval > 0 ? 1 : 0
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["monitoring.rds.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "rds_monitoring" {
  count              = var.monitoring_interval > 0 ? 1 : 0
  name               = "${var.name_prefix}-rds-monitoring-role"
  assume_role_policy = data.aws_iam_policy_document.rds_monitoring_assume[0].json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  count      = var.monitoring_interval > 0 ? 1 : 0
  role       = aws_iam_role.rds_monitoring[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# Optional server-side TLS enforcement. The application already connects with
# verified TLS; this makes MySQL itself reject any unencrypted connection.
# Opt-in (default off) because creating a parameter group needs extra IAM
# permissions on the deploy role, and because RDS applies a changed parameter
# group association at the next reboot (no downtime is caused by the apply).
resource "aws_db_parameter_group" "tls" {
  count       = var.enforce_tls && var.parameter_group_name == null ? 1 : 0
  name_prefix = "${var.name_prefix}-mysql-tls-"
  family      = var.parameter_group_family
  description = "Require TLS for all MySQL connections"

  parameter {
    name         = "require_secure_transport"
    value        = "1"
    apply_method = "immediate"
  }

  tags = var.tags

  lifecycle {
    create_before_destroy = true
  }
}

locals {
  effective_parameter_group = var.parameter_group_name != null ? var.parameter_group_name : try(aws_db_parameter_group.tls[0].name, null)
}

resource "aws_db_instance" "main" {
  identifier = var.db_identifier

  engine         = "mysql"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = var.kms_key_id

  multi_az = var.multi_az

  db_name  = var.db_name
  username = var.db_username

  # No plaintext password anywhere (Terraform, state, Git, CI logs).
  # RDS creates and rotates the master password in AWS Secrets Manager;
  # applications read it from Secrets Manager at runtime, never from a
  # Terraform variable.
  manage_master_user_password = true

  parameter_group_name = local.effective_parameter_group

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.db_sg_id]
  publicly_accessible    = false
  copy_tags_to_snapshot  = true

  backup_retention_period   = var.backup_retention_period
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.db_identifier}-final-${formatdate("YYYYMMDD-hhmm", timestamp())}"
  deletion_protection       = var.deletion_protection
  # Keep optional storage tuning unset for the small default instance.
  iops               = var.iops
  storage_throughput = var.storage_throughput

  performance_insights_enabled = var.performance_insights_enabled
  monitoring_interval          = var.monitoring_interval
  monitoring_role_arn          = var.monitoring_interval > 0 ? aws_iam_role.rds_monitoring[0].arn : null

  tags = var.tags

  lifecycle {
    ignore_changes = [
      final_snapshot_identifier,
    ]

  }
}
