output "asg_name" {
  value = aws_autoscaling_group.app.name
}

output "launch_template_id" {
  value = aws_launch_template.app.id
}

output "ec2_role_arn" {
  value = aws_iam_role.ec2_ssm.arn
}
