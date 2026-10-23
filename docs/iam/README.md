# GitHub Actions OIDC and Terraform state permissions

The policy JSON files in this directory are **templates/reference policies** and use the placeholder `<ACCOUNT_ID>` instead of a real AWS account number (see [Using the templates](#using-the-templates)). Committing them does not install or update an IAM policy in AWS. The Terraform deploy workflow assumes the role configured in the GitHub Environment variable `AWS_DEPLOY_ROLE_ARN`; that role must already trust this repository's OIDC subject and have the permissions needed for the selected environment.

## Using the templates

Replace `<ACCOUNT_ID>` with your 12-digit AWS account ID, and review the bucket names, the `ecomm-platform-dev-*` role/instance-profile prefixes and the `dev` state key against your own `terraform.tfvars` and `backend.hcl` before creating the policy.

```bash
# Linux / macOS / Git Bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
sed "s/<ACCOUNT_ID>/$ACCOUNT_ID/g" docs/iam/terraform-deploy-policy.json > terraform-deploy-policy.local.json
```

```powershell
# Windows PowerShell
$id = aws sts get-caller-identity --query Account --output text
(Get-Content docs\iam\terraform-deploy-policy.json) -replace '<ACCOUNT_ID>', $id | Set-Content terraform-deploy-policy.local.json
```

Keep the rendered `*.local.json` out of Git (add it to your local exclude file). The same placeholder convention applies to the state bucket, `ecomm-platform-tfstate-<ACCOUNT_ID>`, and the CloudTrail bucket, `ecomm-platform-dev-cloudtrail-<ACCOUNT_ID>`.

## Fixing the S3 `HeadObject` 403

For the current dev workflow, confirm the following before running Terraform again:

1. In GitHub **Settings → Environments → dev → Environment variables**, verify `AWS_DEPLOY_ROLE_ARN`, `TF_STATE_BUCKET`, and `AWS_REGION` (normally `us-east-1`). The bucket must be `ecomm-platform-tfstate-<ACCOUNT_ID>` if that is where the existing state lives.
2. In AWS IAM, open the exact role shown by the workflow's **Verify AWS identity** step. Confirm its trust policy permits `repo:karimrabiee/AWS-Secure-Scalable-Web-Application-Architecture:environment:dev` and audience `sts.amazonaws.com`.
3. Confirm the role has `s3:GetObject` and `s3:PutObject` on the exact dev state and lock objects, `s3:DeleteObject` only on the `.tflock` object, and `s3:ListBucket` on the bucket `ecomm-platform-tfstate-<ACCOUNT_ID>` **without** an `s3:prefix` condition. S3 returns **403 instead of 404** for a missing key when the caller lacks an unconditional `s3:ListBucket`, and `HeadObject` requests carry no `s3:prefix` context, so a prefix condition silently turns "object not found" into `Forbidden` (this is also the layout in HashiCorp's S3 backend documentation). The reference policy uses the bucket name shown in the failing run. Use it as a reviewable template, not as proof that the policy is attached.
4. Review the bucket policy, any permissions boundary or Organizations SCP, and the KMS key policy if the object uses a customer-managed KMS key. An explicit deny overrides an IAM allow.
5. Re-run the manual workflow and inspect **Diagnose existing state object access**. A 403 must be corrected; do not enable `allow_fresh_state` to bypass it.

## Safety notes

- Never delete, rename, or recreate the existing Terraform state to resolve a permissions error.
- Never use `AdministratorAccess` as a workaround.
- The policy template currently describes the **dev** role and state prefix; do not reuse it unchanged for prod. Prod requires its own trust conditions, state prefix, and least-privilege policy. The state object itself deliberately has no `s3:DeleteObject` grant; only the lock file can be deleted by this policy.
- The workflow uses native S3 lockfiles (`use_lockfile = true`), so the role needs the corresponding permissions on the `.tflock` object.
