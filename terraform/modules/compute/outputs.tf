output "asg_name" {
  value = aws_autoscaling_group.app.name
}

output "launch_template_id" {
  value = aws_launch_template.app.id
}

output "ec2_role_arn" {
  value = aws_iam_role.ec2_ssm.arn
}

output "app_bucket" {
  description = "Private S3 bucket holding application releases."
  value       = aws_s3_bucket.app.id
}

output "app_release" {
  description = "Content hash of the application release currently deployed."
  value       = local.app_release
}
