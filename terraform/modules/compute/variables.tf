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

variable "enable_instance_refresh" {
  description = "Roll instances automatically when the launch template changes (AMI update, user-data change) instead of manual replacement."
  type        = bool
  default     = true
}

variable "db_secret_arn" {
  description = "ARN of the Secrets Manager secret holding the RDS master credentials (module.database.master_user_secret_arn). The EC2 role is granted secretsmanager:GetSecretValue scoped to exactly this ARN - nothing broader."
  type        = string
}

variable "db_address" {
  description = "RDS hostname (not secret - the security boundary is the security group, not hiding the endpoint)."
  type        = string
}

variable "db_port" {
  type    = number
  default = 3306
}

variable "db_name" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
