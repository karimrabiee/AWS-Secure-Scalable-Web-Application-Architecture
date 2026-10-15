variable "name_prefix" {
  type = string
}

variable "launch_template_name" {
  type = string
}

variable "asg_name" {
  type = string
}

variable "app_subnet_ids" {
  type = list(string)
}

variable "app_sg_id" {
  type = string
}

variable "target_group_arn" {
  type = string
}

variable "instance_type" {
  type    = string
  default = "t2.micro"
}

variable "ami_id" {
  description = <<-EOT
    Optional. Leave null (the default) to auto-discover the latest Amazon
    Linux 2023 AMI via SSM Parameter Store - no manual lookup needed for a
    first deploy. Pin an explicit AMI ID once you want deliberate control
    over exactly when the fleet moves to a new build; combined with
    enable_instance_refresh below, a pinned change still rolls out safely
    instead of replacing instances on every apply. See the AMI update
    procedure in docs/OPERATIONS.md.
  EOT
  type        = string
  default     = null
}

variable "asg_min_size" {
  type    = number
  default = 2
}

variable "asg_desired_capacity" {
  type    = number
  default = 2
}

variable "asg_max_size" {
  type    = number
  default = 4
}

variable "enable_cpu_scaling" {
  description = "Enable target tracking that scales the ASG around the configured average CPU target."
  type        = bool
  default     = true
}

variable "cpu_target_percentage" {
  description = "Average ASG CPU percentage that target tracking tries to maintain."
  type        = number
  default     = 60

  validation {
    condition     = var.cpu_target_percentage > 0 && var.cpu_target_percentage < 100
    error_message = "cpu_target_percentage must be greater than 0 and less than 100."
  }
}

variable "db_address" {
  description = "RDS endpoint host name (no port) the application connects to."
  type        = string
}

variable "db_port" {
  description = "RDS port."
  type        = number
  default     = 3306
}

variable "db_name" {
  description = "Database (schema) name used by the application."
  type        = string
}

variable "db_secret_arn" {
  description = "ARN of the Secrets Manager secret holding the RDS-managed master credentials. The instance role is granted read access to this single secret."
  type        = string
}

variable "health_check_grace_period" {
  description = "Seconds the ASG waits before evaluating ELB health of a new instance (bootstrap installs packages and dependencies)."
  type        = number
  default     = 600
}

variable "enable_instance_refresh" {
  description = "Roll instances automatically when the launch template changes (AMI update, user-data change) instead of manual replacement."
  type        = bool
  default     = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
