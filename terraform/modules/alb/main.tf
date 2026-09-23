resource "aws_lb" "main" {
  name = var.alb_name
  # internal false means the ALB is internet-facing, which is what we want for public access
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_sg_id]
  subnets            = var.public_subnet_ids
  tags               = merge(var.tags, { Name = var.alb_name })
}

#target group for the app tier, which is the only tier that receives traffic from the ALB
resource "aws_lb_target_group" "app" {
  name     = "${var.name_prefix}-tg"
  port     = 80
  protocol = "HTTP"
  vpc_id   = var.vpc_id

  # Health check configuration for the target group this value becauese the ALB needs to know if the app tier
  # is healthy and can receive traffic. If the health check fails, the ALB will stop sending traffic to that target group.
  health_check {
    protocol            = "HTTP"
    path                = var.health_check_path
    healthy_threshold   = var.health_check_healthy_threshold
    unhealthy_threshold = var.health_check_unhealthy_threshold
    interval            = var.health_check_interval
    timeout             = 5
    matcher             = "200"
  }

  tags = var.tags
}

# HTTP always exists (port 80 must stay open at the SG level for the
# ACME/health-check path and for browsers that type http:// manually), but
# it only ever redirects - it never forwards traffic to the app tier once a
# certificate is available. Before a certificate exists (dev bootstrapping),
# it forwards directly so the environment is still testable over HTTP.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  dynamic "default_action" {
    for_each = var.certificate_arn == null ? [1] : []
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.app.arn
    }
  }

  dynamic "default_action" {
    for_each = var.certificate_arn != null ? [1] : []
    content {
      type = "redirect"
      redirect {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }
}

resource "aws_lb_listener" "https" {
  count             = var.certificate_arn != null ? 1 : 0
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}
