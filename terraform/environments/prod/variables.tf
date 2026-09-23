variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "ecomm-platform"
}

variable "availability_zones" {
  type    = list(string)
  default = ["us-east-1a", "us-east-1b"]
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "app_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.11.0/24", "10.0.12.0/24"]
}

variable "db_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.21.0/24", "10.0.22.0/24"]
}

# High availability: prod always runs 2 NAT Gateways, one per AZ.
variable "nat_gateway_count" {
  type    = number
  default = 2
}

variable "certificate_arn" {
  description = "Optional ACM certificate ARN. Leave null for HTTP-only deployment without a domain."
  type        = string
  default     = null
}

variable "ami_id" {
  description = "Optional. Leave null to auto-discover the latest Amazon Linux 2023 AMI via SSM Parameter Store; pin an explicit AMI ID for deliberate, controlled updates once the environment is stable."
  type        = string
  default     = null
}

variable "instance_type" {
  type    = string
  default = "t3.micro"
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

# No default on purpose: this forces a deliberate, explicit choice instead
# of silently picking one. Confirm against the real instance if migrating,
# or size for expected peak load (see docs/OPERATIONS.md) if this is a new
# prod instance.
variable "db_instance_class" {
  type = string
}

variable "db_name" {
  description = "The app's products table lives in this database - needs a real value since the minimal app workload actually connects."
  type        = string
  default     = "appdb"
}

variable "db_username" {
  description = "Master username (not a secret - only the password is, and the password is never a Terraform value at all - see modules/database)."
  type        = string
  default     = "appadmin"
}

variable "alarm_email" {
  description = "Set via TF_VAR_alarm_email or a gitignored tfvars file - never commit a real address."
  type        = string
  default     = null
}

variable "waf_rate_limit_per_5min" {
  type    = number
  default = 2000
}
