variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "enable_https" {
  description = "Whether the ALB SG opens 443. False only before an ACM cert exists (bootstrap order in dev)."
  type        = bool
  default     = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
