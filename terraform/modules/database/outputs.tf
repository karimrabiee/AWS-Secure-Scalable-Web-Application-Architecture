output "db_endpoint" {
  value     = aws_db_instance.main.endpoint
  sensitive = true
}

output "db_instance_id" {
  value = aws_db_instance.main.id
}

output "master_user_secret_arn" {
  description = "Secrets Manager ARN holding the RDS master credentials. Applications read from this at runtime; it is never rendered in plaintext by Terraform."
  value       = try(aws_db_instance.main.master_user_secret[0].secret_arn, null)
  sensitive   = true
}
