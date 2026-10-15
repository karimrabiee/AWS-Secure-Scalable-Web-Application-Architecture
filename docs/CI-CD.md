# CI/CD

Two workflows with a strict separation: **CI** validates everything without AWS credentials;
**Deploy** is manual, serialized, OIDC-authenticated and approval-gated.

## CI (`.github/workflows/ci.yml`)

Runs on pull requests and pushes to `main`. Read-only permissions, no AWS access, never applies.

| Job | What it proves |
|---|---|
| `python` (3.9 and 3.12) | `ruff`, compile, the full pytest suite with coverage, `pip-audit` of runtime dependencies. 3.9 matches Amazon Linux 2023. |
| `mysql-integration` | Real DDL, idempotent seed, `LIKE`/`ESCAPE` semantics and the status probe against a `mysql:8.4` service container. |
| `terraform` (bootstrap, dev, prod) | `terraform fmt -check`, backend-free `init`, `validate`. |
| `hygiene` | No secrets, state/plan files or merge-conflict markers; shell scripts parse. |

The pytest suite also contains *contract tests*: they render the EC2 bootstrap template and run
`bash -n` on it, check that template variables match the Terraform call, that the instance role can
read only one secret, that the release bucket is private/TLS-only, that workflows are valid and use
the correct state key, and that no CRLF or conflict markers exist.

## Deploy (`.github/workflows/terraform-deploy.yml`)

`workflow_dispatch` only: choose `dev` or `prod`, optionally tick *apply*.

1. **Plan job** - OIDC login, `terraform init` (S3 backend), `validate`, **pre-flight**
   (`scripts/preflight.sh`: detects an empty state facing existing resources and VPC quota
   exhaustion), `plan`, plan summary, plan artifact.
2. **Apply job** (only when *apply* is ticked; protected by the GitHub Environment) - applies *that
   exact plan file*, then runs `scripts/smoke-test.sh`: waits for `/health`, verifies the live RDS
   connection over TLS, samples 40 requests (p50/p95/max latency) and records how many Availability
   Zones and instances served traffic. Results land in the run summary.

A per-environment concurrency group prevents overlapping Terraform runs.

### One-time setup (GitHub Environments `dev` and `prod`)

| Environment variable | Required | Notes |
|---|---|---|
| `AWS_DEPLOY_ROLE_ARN` | yes | Role trusted for this repo/environment via GitHub OIDC |
| `TF_STATE_BUCKET` | yes | Bucket created by `terraform/bootstrap` |
| `AWS_REGION` | no | Defaults to `us-east-1` |
| `TF_STATE_KEY` | no | Defaults to `ecomm-platform/<env>/terraform.tfstate`. **Must equal the key the environment was first created with.** |
| `TF_DB_INSTANCE_CLASS` | prod | No default on purpose |
| `TF_ALARM_EMAIL` | no | SNS alert subscriber |

Add required reviewers to the `prod` environment.

### Permissions the deploy role needs for the application release

In addition to the networking, compute, database and monitoring permissions, the role must be
allowed to manage the release bucket and the instance role's inline policies:

* S3 on `arn:aws:s3:::ecomm-platform-<env>-app-*` and `.../*`: `CreateBucket`, `DeleteBucket`,
  `PutBucketPolicy`, `GetBucketPolicy`, `DeleteBucketPolicy`, `PutBucketPublicAccessBlock`,
  `GetBucketPublicAccessBlock`, `PutBucketOwnershipControls`, `GetBucketOwnershipControls`,
  `PutEncryptionConfiguration`, `GetEncryptionConfiguration`, `GetBucketTagging`, `PutBucketTagging`,
  `ListBucket`, `GetBucketLocation`, `GetBucketVersioning`, `GetAccelerateConfiguration`,
  `GetBucketAcl`, `GetBucketCORS`, `GetBucketWebsite`, `GetBucketLogging`, `GetLifecycleConfiguration`,
  `GetReplicationConfiguration`, `GetBucketRequestPayment`, `GetBucketObjectLockConfiguration`,
  `PutObject`, `GetObject`, `DeleteObject`, `GetObjectTagging`, `PutObjectTagging`, `ListBucketVersions`.
* IAM on the instance role: `PutRolePolicy`, `GetRolePolicy`, `DeleteRolePolicy`, `ListRolePolicies`.
* `secretsmanager:DescribeSecret` / `GetSecretValue` is **not** required by Terraform (RDS manages
  the secret); only the instances read it at runtime.

A missing permission appears as an explicit `AccessDenied` on the first apply, naming the action.

## Local checks

```bash
python3 -m venv .venv && . .venv/bin/activate
python -m pip install -r requirements-dev.txt
ruff check .
pytest -q --cov=terraform/modules/compute/app-src --cov-report=term-missing
python scripts/check-repository-hygiene.py
terraform fmt -check -recursive terraform
for root in terraform/bootstrap terraform/environments/dev terraform/environments/prod; do
  (cd "$root" && terraform init -backend=false && terraform validate)
done
```

Run the MySQL integration tests locally against any MySQL 8 server:
`TEST_MYSQL_HOST=127.0.0.1 TEST_MYSQL_PASSWORD=... pytest tests/test_integration_mysql.py`.

## Evidence boundary

CI proves code, configuration and contracts. Only a real deploy (plus the smoke test) proves AWS
permissions, quotas, networking, WAF behaviour, failover and scaling.
