output "db_endpoint" {
  description = "Endpoint in host:port form."
  value       = aws_db_instance.main.endpoint
}

output "db_address" {
  description = "RDS host name (no port)."
  value       = aws_db_instance.main.address
}

output "db_port" {
  description = "RDS port."
  value       = aws_db_instance.main.port
}

output "db_name" {
  description = "Database (schema) name."
  value       = var.db_name
}

output "db_instance_id" {
  value = aws_db_instance.main.id
}

output "master_user_secret_arn" {
  description = "ARN of the Secrets Manager secret holding the RDS-managed master credentials. An ARN is an identifier, not a secret; the password itself is never exposed by Terraform."
  value       = try(nonsensitive(aws_db_instance.main.master_user_secret[0].secret_arn), null)
}
