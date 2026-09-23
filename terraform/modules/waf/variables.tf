variable "name_prefix" {
  type = string
}

variable "alb_arn" {
  type = string
}

variable "rate_limit_per_5min" {
  description = "Requests from one IP exceeding this count in 5 minutes get BLOCKed. AWS WAF rate-based rules evaluate over a rolling 5-minute window; this is not an exact rate limiter (see docs/DECISIONS.md)."
  type        = number
  default     = 2000
}

variable "log_retention_days" {
  type    = number
  default = 90
}

variable "tags" {
  type    = map(string)
  default = {}
}
