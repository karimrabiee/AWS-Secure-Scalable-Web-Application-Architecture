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
  default = "10.1.0.0/16" # distinct range from prod so the two could theoretically peer later
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.1.1.0/24", "10.1.2.0/24"]
}

variable "app_subnet_cidrs" {
  type    = list(string)
  default = ["10.1.11.0/24", "10.1.12.0/24"]
}

variable "db_subnet_cidrs" {
  type    = list(string)
  default = ["10.1.21.0/24", "10.1.22.0/24"]
}

# Cost: 1 NAT in dev - documented, accepted trade-off (see
# modules/networking/variables.tf and docs/DECISIONS.md). Dev
# carries no customer traffic, so a single NAT's AZ dependency is acceptable.
variable "nat_gateway_count" {
  type    = number
  default = 1
}

# No cert in dev by default - HTTP only, documented trade-off.
variable "certificate_arn" {
  type    = string
  default = null
}

variable "instance_type" {
  type    = string
  default = "t3.micro"
}

variable "ami_id" {
  description = "Optional. Leave null to auto-discover the latest Amazon Linux 2023 AMI via SSM Parameter Store."
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

# Smallest viable class in dev - never the larger prod instance class here.
variable "db_instance_class" {
  type    = string
  default = "db.t3.micro"
}

variable "db_name" {
  type    = string
  default = "appdb"
}

variable "db_username" {
  type    = string
  default = "appadmin"
}

variable "alarm_email" {
  type    = string
  default = null
}

variable "waf_rate_limit_per_5min" {
  type    = number
  default = 2000
}
