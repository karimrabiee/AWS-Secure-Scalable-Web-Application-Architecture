# High availability: every resource in this module spans both AZs.
# See docs/DECISIONS.md for the reasoning.

locals {
  azs = { a = var.availability_zones[0], b = var.availability_zones[1] }

  public_cidrs = { a = var.public_subnet_cidrs[0], b = var.public_subnet_cidrs[1] }
  app_cidrs    = { a = var.app_subnet_cidrs[0], b = var.app_subnet_cidrs[1] }
  db_cidrs     = { a = var.db_subnet_cidrs[0], b = var.db_subnet_cidrs[1] }

  # First N azs (by key order a, b) get a NAT Gateway, based on nat_gateway_count.
  nat_az_keys = slice(["a", "b"], 0, var.nat_gateway_count)
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(var.tags, { Name = "${var.name_prefix}-vpc" })
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = merge(var.tags, { Name = "${var.name_prefix}-igw" })
}

resource "aws_subnet" "public" {
  for_each                = local.public_cidrs
  vpc_id                  = aws_vpc.main.id
  cidr_block              = each.value
  availability_zone       = local.azs[each.key]
  map_public_ip_on_launch = true
  tags                    = merge(var.tags, { Name = "${var.name_prefix}-public-${each.key}", Tier = "public" })
}

resource "aws_subnet" "app" {
  for_each          = local.app_cidrs
  vpc_id            = aws_vpc.main.id
  cidr_block        = each.value
  availability_zone = local.azs[each.key]
  tags              = merge(var.tags, { Name = "${var.name_prefix}-app-${each.key}", Tier = "app-private" })
}

resource "aws_subnet" "db" {
  for_each          = local.db_cidrs
  vpc_id            = aws_vpc.main.id
  cidr_block        = each.value
  availability_zone = local.azs[each.key]
  tags              = merge(var.tags, { Name = "${var.name_prefix}-db-${each.key}", Tier = "db-private" })
}

# --- NAT: count driven by var.nat_gateway_count (cost control in dev) ---

resource "aws_eip" "nat" {
  for_each = toset(local.nat_az_keys)
  domain   = "vpc"
  tags     = merge(var.tags, { Name = "${var.name_prefix}-nat-eip-${each.key}" })
}

resource "aws_nat_gateway" "main" {
  for_each      = toset(local.nat_az_keys)
  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = aws_subnet.public[each.key].id
  tags          = merge(var.tags, { Name = "${var.name_prefix}-nat-${each.key}" })
  depends_on    = [aws_internet_gateway.main]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  tags   = merge(var.tags, { Name = "${var.name_prefix}-public-rt" })
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.main.id
}

resource "aws_route_table_association" "public" {
  for_each       = local.public_cidrs
  subnet_id      = aws_subnet.public[each.key].id
  route_table_id = aws_route_table.public.id
}

# App-private route tables: one per AZ when nat_gateway_count = 2 (each AZ
# routes to its own NAT); when nat_gateway_count = 1, both AZs route to the
# single NAT (documented, accepted trade-off for dev - see variables.tf).
resource "aws_route_table" "app_private" {
  for_each = local.azs
  vpc_id   = aws_vpc.main.id
  tags     = merge(var.tags, { Name = "${var.name_prefix}-app-rt-${each.key}" })
}

resource "aws_route" "app_private_nat" {
  for_each               = local.azs
  route_table_id         = aws_route_table.app_private[each.key].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = contains(local.nat_az_keys, each.key) ? aws_nat_gateway.main[each.key].id : aws_nat_gateway.main[local.nat_az_keys[0]].id
}

resource "aws_route_table_association" "app" {
  for_each       = local.app_cidrs
  subnet_id      = aws_subnet.app[each.key].id
  route_table_id = aws_route_table.app_private[each.key].id
}

# DB-private: no default route at all (isolation control).
resource "aws_route_table" "db_private" {
  for_each = local.azs
  vpc_id   = aws_vpc.main.id
  tags     = merge(var.tags, { Name = "${var.name_prefix}-db-rt-${each.key}" })
}

resource "aws_route_table_association" "db" {
  for_each       = local.db_cidrs
  subnet_id      = aws_subnet.db[each.key].id
  route_table_id = aws_route_table.db_private[each.key].id
}

# --- VPC Flow Logs (centralized audit trail) ---

resource "aws_cloudwatch_log_group" "flow_logs" {
  name              = "/vpc/${var.name_prefix}/flow-logs"
  retention_in_days = var.flow_log_retention_days
  tags              = var.tags
}

data "aws_iam_policy_document" "flow_logs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["vpc-flow-logs.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "flow_logs" {
  name               = "${var.name_prefix}-flow-logs-role"
  assume_role_policy = data.aws_iam_policy_document.flow_logs_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "flow_logs_publish" {
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogGroups", "logs:DescribeLogStreams"]
    resources = ["${aws_cloudwatch_log_group.flow_logs.arn}:*"]
  }
}

resource "aws_iam_role_policy" "flow_logs_publish" {
  name   = "${var.name_prefix}-flow-logs-publish"
  role   = aws_iam_role.flow_logs.id
  policy = data.aws_iam_policy_document.flow_logs_publish.json
}

resource "aws_flow_log" "main" {
  vpc_id               = aws_vpc.main.id
  traffic_type         = "ALL"
  log_destination_type = "cloud-watch-logs"
  log_destination      = aws_cloudwatch_log_group.flow_logs.arn
  iam_role_arn         = aws_iam_role.flow_logs.arn
  tags                 = var.tags
}
