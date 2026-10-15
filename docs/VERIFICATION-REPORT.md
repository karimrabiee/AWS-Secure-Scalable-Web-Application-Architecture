# Verification Report

**Scope:** repository-level verification performed in a sandbox without AWS credentials,
Terraform or a MySQL server. Nothing here claims a live AWS result.

## Results

| Check | Method | Result |
|---|---|---|
| Application and contract tests | `python -m unittest discover -s tests` (identical tests run under pytest in CI) | **71 tests: 67 passed, 4 skipped** (MySQL integration, CI-only), 0 failed |
| Bootstrap script | Rendered like `templatefile()`, `bash -n` | Valid syntax; **7.7 KB** of the 16 KB EC2 user-data limit |
| Repository hygiene | `scripts/check-repository-hygiene.py` | Pass: no secrets, state/plan files or conflict markers |
| Line endings | contract test | LF everywhere |
| Python 3.9 compatibility | `ast.parse(feature_version=(3, 9))` | Pass |
| Terraform `fmt` / `validate` | **Not run here** (no Terraform binary) | Executed by CI on every PR |
| MySQL 8.4 integration | **Not run here** | Executed by the `mysql-integration` CI job |
| AWS plan/apply, failover, scaling, load test | **Not run** | Run the deploy workflow; the smoke test records results |

## Defects found and fixed

| Severity | Finding | Fix |
|---|---|---|
| Critical | Merge-conflict markers committed in 11 files, including `ci.yml` (CI could not parse), `user-data.sh.tftpl` and `requirements.txt` (EC2 bootstrap would fail) | Resolved; contract test + hygiene scan now fail on any marker |
| Critical | Deploy workflow used state key `<prefix>/<env>.tfstate`, different from the original `ecomm-platform/<env>/terraform.tfstate`: empty state, hence `EntityAlreadyExists` for IAM roles and `VpcLimitExceeded` | Key defaults to the original convention; pre-flight detects mismatch and quota exhaustion |
| High | Application never used the database (static page) | New `db.py` with Secrets Manager, verified TLS, rotation retry, idempotent schema/seed |
| High | CRLF line endings inside a bash template | Normalised; `.gitattributes` enforces LF; contract test |
| High | Unverified transitive pins (e.g. non-existent versions) could break `pip install` on boot | Direct dependencies pinned only |
| Medium | Terraform state, plan, tfvars and an AI task file in the repository | Removed; contract test forbids them |
| Medium | Docs claimed the app does not query RDS | Rewritten |

## Evidence boundary

Local success proves code and configuration consistency, not AWS permissions, quotas, live failover,
WAF behaviour, scaling or cost.
