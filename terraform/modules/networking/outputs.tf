output "vpc_id" {
  value = aws_vpc.main.id
}

output "public_subnet_ids" {
  value = [for s in aws_subnet.public : s.id]
}

output "app_subnet_ids" {
  value = [for s in aws_subnet.app : s.id]
}

output "db_subnet_ids" {
  value = [for s in aws_subnet.db : s.id]
}

output "vpc_cidr" {
  value = aws_vpc.main.cidr_block
}
