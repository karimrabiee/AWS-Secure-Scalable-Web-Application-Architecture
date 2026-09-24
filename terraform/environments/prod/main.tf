locals {
  name_prefix = "${var.project_name}-prod"
  tags = {
    Project     = var.project_name
    Environment = "prod"
  }
}

module "networking" {
  source = "../../modules/networking"

  name_prefix         = local.name_prefix
  vpc_cidr            = var.vpc_cidr
  availability_zones  = var.availability_zones
  public_subnet_cidrs = var.public_subnet_cidrs
  app_subnet_cidrs    = var.app_subnet_cidrs
  db_subnet_cidrs     = var.db_subnet_cidrs
  nat_gateway_count   = var.nat_gateway_count
  tags                = local.tags
}

module "security" {
  source = "../../modules/security"

  name_prefix  = local.name_prefix
  vpc_id       = module.networking.vpc_id
  enable_https = var.certificate_arn != null
  tags         = local.tags
}


module "alb" {
  source = "../../modules/alb"

  name_prefix       = local.name_prefix
  alb_name          = "Production-ALB"
  vpc_id            = module.networking.vpc_id
  public_subnet_ids = module.networking.public_subnet_ids
  alb_sg_id         = module.security.alb_sg_id
  certificate_arn   = var.certificate_arn
  health_check_path = "/health"
  tags              = local.tags
}

module "waf" {
  source = "../../modules/waf"

  name_prefix         = local.name_prefix
  alb_arn             = module.alb.alb_arn
  rate_limit_per_5min = var.waf_rate_limit_per_5min
  tags                = local.tags
}

module "database" {
  source = "../../modules/database"

  name_prefix         = local.name_prefix
  db_identifier       = "production-db"
  db_subnet_ids       = module.networking.db_subnet_ids
  db_sg_id            = module.security.db_sg_id
  instance_class      = var.db_instance_class
  db_name             = var.db_name
  db_username         = var.db_username
  multi_az            = true
  deletion_protection = true
  tags                = local.tags
}

module "compute" {
  source = "../../modules/compute"

  name_prefix           = local.name_prefix
  launch_template_name  = "Production-LT"
  asg_name              = "Production-ASG"
  app_subnet_ids        = module.networking.app_subnet_ids
  app_sg_id             = module.security.app_sg_id
  target_group_arn      = module.alb.target_group_arn
  instance_type         = var.instance_type
  ami_id                = var.ami_id
  asg_min_size          = var.asg_min_size
  asg_desired_capacity  = var.asg_desired_capacity
  asg_max_size          = var.asg_max_size
  enable_cpu_scaling    = var.enable_cpu_scaling
  cpu_target_percentage = var.cpu_target_percentage
  db_secret_arn         = module.database.master_user_secret_arn
  db_address            = module.database.db_address
  db_port               = module.database.db_port
  db_name               = var.db_name
  tags                  = local.tags
}

module "monitoring" {
  source = "../../modules/monitoring"

  name_prefix             = local.name_prefix
  sns_topic_name          = "Production-Alerts"
  alarm_email             = var.alarm_email
  asg_name                = module.compute.asg_name
  alb_arn_suffix          = module.alb.alb_arn_suffix
  target_group_arn_suffix = module.alb.target_group_arn_suffix
  db_instance_id          = module.database.db_instance_id
  tags                    = local.tags
}

module "security_services" {
  source = "../../modules/security-services"

  name_prefix = local.name_prefix
  tags        = local.tags
}
