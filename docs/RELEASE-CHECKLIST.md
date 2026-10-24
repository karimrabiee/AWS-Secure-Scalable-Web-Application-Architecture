# Release checklist

Use this checklist before merging or deploying. It is intentionally small: the project should stay understandable and affordable.

## Pull request checks

- [ ] GitHub Actions CI is green for Python 3.11 and 3.12.
- [ ] Unit, infrastructure-contract and MySQL integration tests are green; skipped database tests are understood.
- [ ] `ruff check .`, `pip-audit`, repository hygiene and workflow lint are green.
- [ ] `terraform fmt -check -recursive terraform` is green.
- [ ] Terraform `init -backend=false` and `validate` are green for bootstrap, dev and prod.
- [ ] No state file, plan, `terraform.tfvars`, `backend.hcl`, credential or private key is present.
- [ ] The plan does not introduce a new public path to EC2 or RDS.

## Before a dev deployment

- [ ] The AWS account and region are confirmed.
- [ ] The bootstrap state bucket exists and its backend configuration points to the intended account.
- [ ] The environment's remote state object is readable by the OIDC role.
- [ ] The OIDC trust policy is limited to this repository and the intended branch/environment.
- [ ] The VPC quota and IAM role names are checked if a previous apply was interrupted.
- [ ] A monthly AWS Budget alert is configured.
- [ ] `dev` is selected first; NAT Gateway, RDS, ALB and WAF still incur charges.

## Before a prod deployment

- [ ] A real ACM certificate ARN is configured; HTTPS is not assumed when the value is absent.
- [ ] `TF_DB_INSTANCE_CLASS` is set deliberately.
- [ ] `TF_ALARM_EMAIL` is set and the SNS confirmation email is completed.
- [ ] RDS deletion protection, Multi-AZ, backup retention and storage settings are reviewed.
- [ ] The plan has no unexpected delete or replace actions.
- [ ] A rollback or recovery decision exists for every planned database or network change.

## After apply

- [ ] The workflow's saved plan is the artifact that was applied.
- [ ] `/health` returns `200` through the ALB.
- [ ] `/ready` returns `200` and shows the database as connected.
- [ ] Two targets are healthy in `dev` and the intended number are healthy in `prod`.
- [ ] The storefront can read products and a demo order is written to RDS.
- [ ] SSM shows the instances as managed; no SSH rule exists.
- [ ] WAF, CloudWatch alarms, CloudTrail and Flow Logs are checked in the target account.
- [ ] The output and evidence contain no account IDs, public IPs, email addresses or secret values.

A green CI run is not proof of a successful AWS deployment. A successful Terraform apply is not proof of application readiness until the bounded smoke tests and the checks above pass.
