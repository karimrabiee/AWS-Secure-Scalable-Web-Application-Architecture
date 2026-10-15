# CI/CD

Two workflows, deliberately separate:

| Workflow | Trigger | AWS access | Does |
|---|---|---|---|
| `ci.yml` | push / PR | none | lint, tests (Python 3.11 + 3.12, real `mysql:8.4` service), Terraform fmt + backend-free validate, hygiene, `actionlint`, `pip-audit`, advisory Checkov |
| `terraform-deploy.yml` | manual (`workflow_dispatch`) | OIDC role | plan → approval → apply of the saved plan → smoke test |

## Deployment workflow

Inputs: `environment` (dev/prod), `apply`, `allow_fresh_state`, `allow_destroy`.

1. **Plan job** – OIDC login, `terraform init` against the fixed backend, guards, `terraform plan -out`, plan summary in the run page, plan uploaded as an artifact.
2. **Apply job** (only if `apply` is ticked, `needs: plan`) – runs in the GitHub Environment, so *required reviewers* gate it. It applies the **same saved plan** (a stale or different plan is rejected by Terraform), then curls `/health` and `/ready` on the ALB.

Safety properties: per-environment `concurrency` group (no parallel runs), `-lock-timeout=300s`, masked account id in logs, `contents: read` + `id-token: write` only.

### State location (the root cause of the failed run)

```
bucket: <TF_STATE_BUCKET>            e.g. ecomm-platform-tfstate-<account-id>
key:    ecomm-platform/<env>/terraform.tfstate
region: AWS_REGION (default us-east-1)
```

This is exactly the key in `terraform/environments/<env>/backend.hcl.example`. The earlier workflow used `${TF_STATE_KEY_PREFIX}/<env>.tfstate`, a **different object**. Terraform therefore saw an empty state and tried to create everything that the local state already tracked: `EntityAlreadyExists` (IAM roles), `VpcLimitExceeded`. The variable `TF_STATE_KEY_PREFIX` no longer exists; delete it from the GitHub Environment.

Guards that stop it recurring:
- **Empty state** → job fails unless `allow_fresh_state` is ticked (first deployment only).
- **Deletes/replacements in the plan** → job fails unless `allow_destroy` is ticked.

### Required GitHub Environment variables

| Variable | Required | Note |
|---|---|---|
| `AWS_DEPLOY_ROLE_ARN` | yes | e.g. `arn:aws:iam::<account>:role/GitHubActions-Terraform-Dev` |
| `TF_STATE_BUCKET` | yes | existing bucket from `terraform/bootstrap` |
| `AWS_REGION` | no | default `us-east-1` |
| `TF_DB_INSTANCE_CLASS` | prod only | no default by design |
| `TF_ALARM_EMAIL` | no | SNS email subscription |

Add required reviewers to the `prod` Environment.

## Recovering from a wrong state key (read-only runbook)

1. List what the bucket really contains (read-only):
   ```bash
   scripts/state-inventory.sh <state-bucket> us-east-1
   ```
   Look for the object with many resources (normally `ecomm-platform/dev/terraform.tfstate`). A `.tflock` file means a run is active or crashed.
2. Confirm the same key locally: `terraform -chdir=terraform/environments/dev init -backend-config=backend.hcl && terraform state list | wc -l`.
3. Run the workflow with `apply` **unticked**; read the plan summary. A healthy plan on an existing stack is small (mostly updates/no-ops).
4. Never delete state, never `terraform import` blindly, never rename resources to dodge `EntityAlreadyExists`. If a crashed run left a lock, confirm nothing is running, then `terraform force-unlock <ID>`.

## IAM for the deploy role

Reference documents: `docs/iam/github-oidc-trust-policy.json` (trust restricted to this repo and the Environment) and `docs/iam/terraform-deploy-policy.json`.

- `iam:PassRole` only for project roles (`ecomm-platform-*`) and only to `ec2.amazonaws.com` / `monitoring.rds.amazonaws.com`.
- Object access (`GetObject`/`PutObject`) limited to the exact state key and its `.tflock`; `DeleteObject` only on the `.tflock`.
- `s3:ListBucket` on the state bucket **without** an `s3:prefix` condition. `HeadObject`/`GetObject` carry no prefix context, so a prefix condition turns a missing or readable object into `403 Forbidden` (this was the cause of the `HeadObject 403` seen in the plan job). See `docs/iam/README.md`.
- The app now creates an inline policy on the EC2 role, so the role also needs `iam:PutRolePolicy`, `iam:GetRolePolicy`, `iam:DeleteRolePolicy`. If `enforce_tls` is used, RDS parameter-group actions (`rds:CreateDBParameterGroup`, `rds:ModifyDBParameterGroup`, `rds:DeleteDBParameterGroup`, `rds:DescribeDBParameterGroups`, `rds:DescribeDBParameters`) are needed too.

## Local checks

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r terraform/modules/compute/app-src/requirements.txt -r requirements-dev.txt
python -m pytest -q                       # DB integration tests skip unless TEST_DB_HOST is set
TEST_DB_HOST=127.0.0.1 TEST_DB_USER=root python -m pytest -q   # with a local MySQL/MariaDB
ruff check . && python scripts/check-repository-hygiene.py
terraform fmt -check -recursive terraform
for r in bootstrap environments/dev environments/prod; do (cd terraform/$r && terraform init -backend=false && terraform validate); done
```

## Evidence boundary

CI proves code and configuration validity only. It does not prove AWS permissions, quotas, provider behaviour, or a successful deployment; those need an authorised run and recorded evidence.
