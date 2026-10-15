# GitHub Actions OIDC and Terraform state permissions

The policy JSON files in this directory are **templates/reference policies**. Committing them does not install or update an IAM policy in AWS. The Terraform deploy workflow assumes the role configured in the GitHub Environment variable `AWS_DEPLOY_ROLE_ARN`; that role must already trust this repository's OIDC subject and have the permissions needed for the selected environment.

## Fixing the S3 `HeadObject` 403

For the current dev workflow, confirm the following before running Terraform again:

1. In GitHub **Settings → Environments → dev → Environment variables**, verify `AWS_DEPLOY_ROLE_ARN`, `TF_STATE_BUCKET`, and `AWS_REGION` (normally `us-east-1`). The bucket must be `ecomm-platform-tfstate-768477844931` if that is where the existing state lives.
2. In AWS IAM, open the exact role shown by the workflow's **Verify AWS identity** step. Confirm its trust policy permits `repo:karimrabiee/AWS-Secure-Scalable-Web-Application-Architecture:environment:dev` and audience `sts.amazonaws.com`.
3. Confirm the role has `s3:GetObject` and `s3:PutObject` on the exact dev state and lock objects, `s3:DeleteObject` only on the `.tflock` object, and `s3:ListBucket` on `ecomm-platform-tfstate-768477844931` with the `ecomm-platform/dev/*` prefix. The reference policy now uses the bucket name shown in the failing run. Use it as a reviewable template, not as proof that the policy is attached.
4. Review the bucket policy, any permissions boundary or Organizations SCP, and the KMS key policy if the object uses a customer-managed KMS key. An explicit deny overrides an IAM allow.
5. Re-run the manual workflow and inspect **Diagnose existing state object access**. A 403 must be corrected; do not enable `allow_fresh_state` to bypass it.

## Safety notes

- Never delete, rename, or recreate the existing Terraform state to resolve a permissions error.
- Never use `AdministratorAccess` as a workaround.
- The policy template currently describes the **dev** role and state prefix; do not reuse it unchanged for prod. Prod requires its own trust conditions, state prefix, and least-privilege policy. The state object itself deliberately has no `s3:DeleteObject` grant; only the lock file can be deleted by this policy.
- The workflow uses native S3 lockfiles (`use_lockfile = true`), so the role needs the corresponding permissions on the `.tflock` object.
