variable "name_prefix" {
  type = string
}

variable "db_identifier" {
  description = "Exact RDS identifier. If migrating an existing instance this must match the real identifier - never invented."
  type        = string
}

variable "db_subnet_ids" {
  type = list(string)
}

variable "db_sg_id" {
  type = string
}

variable "engine_version" {
  type    = string
  default = "8.4.8"
}

variable "instance_class" {
  type = string
}

variable "allocated_storage" {
  type    = number
  default = 20
}

variable "multi_az" {
  description = "Multi-AZ improves availability (automatic failover) but is NOT a substitute for backups/PITR - see docs/OPERATIONS.md."
  type        = bool
  default     = true
}

variable "backup_retention_period" {
  description = "Days of automated backups. Up to 35 per AWS RDS limits."
  type        = number
  default     = 7
  validation {
    condition     = var.backup_retention_period >= 1 && var.backup_retention_period <= 35
    error_message = "RDS automated backup retention must be between 1 and 35 days."
  }
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "db_name" {
  description = "Database name the application connects to. Given a sensible default so the minimal app workload has somewhere to connect - override if migrating a real existing instance with a different name."
  type        = string
  default     = "appdb"
}

variable "db_username" {
  description = <<-EOT
    Master username. This is a username, not a secret, so it is not
    treated as sensitive - only the password is (and the password is never
    a Terraform variable at all, see manage_master_user_password below).
    A non-null default is required: RDS has no default master username for
    a new instance, unlike most other optional attributes here.
  EOT
  type        = string
  default     = "appadmin"
}

variable "performance_insights_enabled" {
  type    = bool
  default = false
}

variable "monitoring_interval" {
  description = "Enhanced Monitoring interval in seconds (0 disables it). 60s gives OS-level metrics (memory, disk I/O) that CloudWatch's default RDS metrics don't cover."
  type        = number
  default     = 60
}

variable "parameter_group_name" {
  description = "UNKNOWN by default - only set if the real instance uses a non-default parameter group. Never invented."
  type        = string
  default     = null
}

variable "kms_key_id" {
  description = "UNKNOWN by default - if the real instance uses a customer-managed KMS key, set its ARN here. Null uses the AWS-managed default RDS key."
  type        = string
  default     = null
}

variable "max_allocated_storage" {
  description = "Enables RDS storage autoscaling so a slow storage-growth incident doesn't require a manual apply. Set to null to disable (e.g. if the client wants storage growth to always require a deliberate change)."
  type        = number
  default     = 100
}

variable "iops" {
  description = "Optional provisioned IOPS for larger io1/io2 databases; null keeps the default storage behavior."
  type        = number
  default     = null
}

variable "storage_throughput" {
  description = "Optional gp3 throughput in MiB/s for larger databases; null keeps the AWS default."
  type        = number
  default     = null
}

variable "tags" {
  type    = map(string)
  default = {}
}
