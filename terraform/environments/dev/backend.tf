# Partial backend config - concrete values supplied at init time via
# backend.hcl (gitignored; see backend.hcl.example), so no bucket name or
# account-specific detail is hardcoded in a committed file.
#
#   terraform init -backend-config=".\backend.hcl"
#
terraform {
  backend "s3" {
    encrypt      = true
    use_lockfile = true # native S3 state locking (Terraform >= 1.10) - no DynamoDB table needed/used
  }
}
