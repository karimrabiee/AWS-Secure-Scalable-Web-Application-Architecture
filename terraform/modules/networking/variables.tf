variable "name_prefix" {
  description = "Prefix for resource names, e.g. \"ecomm-prod\"."
  type        = string
}

variable "vpc_cidr" {
  type = string
}

variable "availability_zones" {
  description = "Exactly 2 AZs. High availability requires the app to survive a single-AZ failure."
  type        = list(string)
  validation {
    condition     = length(var.availability_zones) == 2
    error_message = "Exactly two AZs are required to satisfy the documented HA requirement."
  }
}

variable "public_subnet_cidrs" {
  type = list(string)
}

variable "app_subnet_cidrs" {
  type = list(string)
}

variable "db_subnet_cidrs" {
  type = list(string)
}

variable "nat_gateway_count" {
  description = <<-EOT
    Number of NAT Gateways: 2 for prod (one per AZ - avoids a
    cross-AZ dependency for outbound traffic, see docs/DECISIONS.md), 1 for dev/cost
    control (documented, accepted trade-off: a NAT failure in dev takes
    down outbound traffic for both AZs - acceptable because dev carries no
    customer traffic, see docs/DECISIONS.md).
  EOT
  type        = number
  validation {
    condition     = contains([1, 2], var.nat_gateway_count)
    error_message = "nat_gateway_count must be 1 (dev) or 2 (prod)."
  }
}

variable "flow_log_retention_days" {
  type    = number
  default = 90
}

variable "tags" {
  type    = map(string)
  default = {}
}
