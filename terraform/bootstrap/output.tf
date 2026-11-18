output "bucket_name" {
  value = aws_s3_bucket.tfstate.bucket
}

output "monthly_budget_name" {
  value = aws_budgets_budget.monthly_account.name
}
