#!/usr/bin/env bash
# Pre-flight guard for Terraform deployments: fail fast, with an actionable message, on the two
# problems that otherwise surface halfway through `terraform apply`:
#
#   1. State/infrastructure mismatch - Terraform's state is empty but the environment's AWS
#      resources already exist (typically because the workflow uses a different state key than
#      the run that created them). Applying would collide with EntityAlreadyExists errors.
#   2. A fresh deployment would exceed the regional VPC quota (VpcLimitExceeded).
#
# Usage: STATE_COUNT=<resources in state> scripts/preflight.sh <dev|prod> [project-name]
# Needs read-only iam:GetRole and ec2:DescribeVpcs; checks degrade to warnings when denied.
set -euo pipefail

ENVIRONMENT=${1:?usage: preflight.sh <dev|prod> [project-name]}
PROJECT=${2:-ecomm-platform}
REGION=${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}
STATE_COUNT=${STATE_COUNT:?export STATE_COUNT (number of resources in the Terraform state)}
PREFIX="${PROJECT}-${ENVIRONMENT}"
VPC_QUOTA_CODE=L-F678F1CE
failed=0

error() { echo "::error title=Pre-flight failed::$*"; failed=1; }
warn() { echo "::warning title=Pre-flight::$*"; }

echo "Environment: $ENVIRONMENT | prefix: $PREFIX | region: $REGION | resources in state: $STATE_COUNT"

if [ "$STATE_COUNT" -eq 0 ]; then
  # --- 1. Orphaned resources -------------------------------------------------
  probe_role="${PREFIX}-ec2-ssm-role"
  if output=$(aws iam get-role --role-name "$probe_role" 2>&1); then
    error "Terraform state is empty, but IAM role '$probe_role' already exists. This usually means the \
workflow's state key differs from the key used by the original apply, or a previous stack was never \
destroyed. Point TF_STATE_KEY at the existing state (default: $PROJECT/$ENVIRONMENT/terraform.tfstate) \
or destroy/import the existing resources. See docs/TROUBLESHOOTING.md#state-mismatch."
  elif grep -q "NoSuchEntity" <<<"$output"; then
    echo "OK: no pre-existing resources found for $PREFIX"
  else
    warn "Could not check for existing IAM resources (needs iam:GetRole): ${output:0:160}"
  fi

  # --- 2. VPC quota ----------------------------------------------------------
  if vpc_count=$(aws ec2 describe-vpcs --region "$REGION" --query 'length(Vpcs)' --output text 2>/dev/null); then
    quota=$(aws service-quotas get-service-quota --region "$REGION" --service-code vpc \
      --quota-code "$VPC_QUOTA_CODE" --query 'Quota.Value' --output text 2>/dev/null || echo 5)
    quota=${quota%.*}
    echo "VPCs in $REGION: $vpc_count of $quota"
    if [ "$vpc_count" -ge "$quota" ]; then
      echo "Existing VPCs:"
      aws ec2 describe-vpcs --region "$REGION" --output table \
        --query 'Vpcs[].{Id:VpcId,Cidr:CidrBlock,Default:IsDefault,Name:Tags[?Key==`Name`]|[0].Value}' || true
      error "Region $REGION already has $vpc_count VPCs (quota $quota); creating another will fail with \
VpcLimitExceeded. Delete unused VPCs (leftovers from earlier test stacks) or request a quota increase \
(Service Quotas > Amazon VPC > 'VPCs per Region')."
    fi
  else
    warn "Could not read VPC count (needs ec2:DescribeVpcs); skipping quota check"
  fi
else
  echo "OK: state already tracks $STATE_COUNT resources; skipping fresh-create checks"
fi

exit "$failed"
