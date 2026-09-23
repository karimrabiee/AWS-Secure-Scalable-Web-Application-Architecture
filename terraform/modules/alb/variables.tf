variable "name_prefix" {
  type = string
}

variable "alb_name" {
  description = "Exact ALB name. If migrating an existing ALB, this must match the real name discovered from AWS - do not let Terraform invent one."
  type        = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "alb_sg_id" {
  type = string
}

variable "certificate_arn" {
  description = <<-EOT
    ACM certificate ARN for the HTTPS listener. Required in prod.
    UNKNOWN until requested/validated in ACM for the real domain - never
    invent an ARN. In dev, leave null to run HTTP-only (documented,
    accepted trade-off - no customer traffic in dev).
  EOT
  type        = string
  default     = null
}

variable "health_check_path" {
  type    = string
  default = "/health"
}

variable "health_check_healthy_threshold" {
  type    = number
  default = 2
}

variable "health_check_unhealthy_threshold" {
  type    = number
  default = 2
}

variable "health_check_interval" {
  type    = number
  default = 30
}

variable "tags" {
  type    = map(string)
  default = {}
}
