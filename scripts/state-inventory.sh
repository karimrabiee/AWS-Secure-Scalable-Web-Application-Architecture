#!/usr/bin/env bash
# READ-ONLY inventory of Terraform state objects in the state bucket.
# Use it to find out WHICH state object actually tracks your infrastructure
# before running any plan/apply (see docs/CI-CD.md, "Recovering from a wrong state key").
# It only calls s3:ListBucket / s3:GetObject. It never writes, moves or deletes anything.
#
# Usage:  scripts/state-inventory.sh <state-bucket> [region]
set -euo pipefail

BUCKET=${1:?usage: $0 <state-bucket> [region]}
REGION=${2:-us-east-1}
command -v aws >/dev/null || { echo "aws CLI is required" >&2; exit 1; }
command -v jq  >/dev/null || { echo "jq is required" >&2; exit 1; }

echo "Bucket: ${BUCKET}  Region: ${REGION}"
printf '%-62s %10s %10s\n' "OBJECT KEY" "BYTES" "RESOURCES"

aws s3api list-objects-v2 --bucket "$BUCKET" --region "$REGION" \
  --query 'Contents[].[Key,Size]' --output text | while read -r key size; do
  case "$key" in
    *.tflock)
      printf '%-62s %10s %10s\n' "$key" "$size" "LOCK (run in progress, or stale after a crash)" ;;
    *.tfstate)
      count=$(aws s3 cp "s3://${BUCKET}/${key}" - --region "$REGION" 2>/dev/null | jq '[.resources[]?] | length' 2>/dev/null || echo "?")
      printf '%-62s %10s %10s\n' "$key" "$size" "$count" ;;
  esac
done

cat <<'MSG'

Reading the result:
  * The state object with the large resource count is the one that tracks your real infrastructure.
  * environments/<env>/backend.hcl and .github/workflows/terraform-deploy.yml must point to THAT key
    (convention: ecomm-platform/<env>/terraform.tfstate).
  * A second, small object (a few resources) is usually left over from a failed CI run. Do not delete
    it blindly: compare `terraform state list` for both keys first (docs/CI-CD.md).
MSG
