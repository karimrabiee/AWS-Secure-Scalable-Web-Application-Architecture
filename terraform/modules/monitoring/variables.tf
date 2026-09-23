variable "name_prefix" {
  type = string
}

variable "sns_topic_name" {
  type = string
}

variable "alarm_email" {
  description = <<-EOT
    Subscriber email for the SNS alerts topic. Default null deliberately -
    do not hardcode a real personal address in tfvars/committed files.
    Set via TF_VAR_alarm_email or an environment-specific tfvars file that
    is gitignored.
  EOT
  type        = string
  default     = null
}

variable "asg_name" {
  type = string
}

variable "alb_arn_suffix" {
  type = string
}

variable "target_group_arn_suffix" {
  type = string
}

variable "db_instance_id" {
  type = string
}

variable "ec2_cpu_threshold_percent" {
  description = <<-EOT
    CloudWatch alarm threshold for average ASG CPU. v1 of this project used
    an undocumented/likely-erroneous value of 1.0 (percent) copied from an
    early manual setup; that value is not carried forward here as it would
    fire constantly. 70% is the value actually used going forward -
    documented explicitly as a deliberate change, not silently inherited.
    Keep this simple and tune it only after observing real traffic.
  EOT
  type        = number
  default     = 70
}

variable "tags" {
  type    = map(string)
  default = {}
}
