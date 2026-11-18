variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "ecomm-platform"
}

variable "budget_limit_usd" {
  description = "Monthly account-level AWS Budget limit in USD. This covers the account, not only Terraform resources."
  type        = number
  default     = 5

  validation {
    condition     = var.budget_limit_usd > 0
    error_message = "budget_limit_usd must be greater than zero."
  }
}

variable "budget_email" {
  description = "Optional email address for AWS Budget alerts. Set via TF_VAR_budget_email or a local, gitignored tfvars file."
  type        = string
  default     = null
}