output "alb_dns_name" {
  value = module.alb.alb_dns_name
}

output "vpc_id" {
  value = module.networking.vpc_id
}

output "asg_name" {
  value = module.compute.asg_name
}

output "db_instance_id" {
  value = module.database.db_instance_id
}

output "rds_master_secret_arn" {
  value     = module.database.master_user_secret_arn
  sensitive = true
}

output "cloudtrail_bucket" {
  value = module.security_services.cloudtrail_bucket
}

output "sns_topic_arn" {
  value = module.monitoring.sns_topic_arn
}
