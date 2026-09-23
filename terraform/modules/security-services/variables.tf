variable "name_prefix" {
  type = string
}

variable "cloudtrail_retention_days" {
  description = "Number of days to keep CloudTrail logs before expiration."
  type        = number
  default     = 365
}

variable "tags" {
  type    = map(string)
  default = {}
}
