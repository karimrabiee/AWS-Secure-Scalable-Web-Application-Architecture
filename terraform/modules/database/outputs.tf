output "db_endpoint" {
  description = "Endpoint in host:port form."
  value       = aws_db_instance.main.endpoint
  sensitive   = true
}

output "db_address" {
  description = "RDS hostname without the port. Not a secret; used for the application connection."
  value       = aws_db_instance.main.address
}

output "db_port" {
  description = "RDS listener port."
  value       = aws_db_instance.main.port
}

output "db_instance_id" {
  value = aws_db_instance.main.id
}

output "master_user_secret_arn" {
  description = "ARN of the RDS-managed Secrets Manager secret. An ARN is an identifier, not a credential; the secret value never appears in state or outputs."
  value       = nonsensitive(try(aws_db_instance.main.master_user_secret[0].secret_arn, null))
}
