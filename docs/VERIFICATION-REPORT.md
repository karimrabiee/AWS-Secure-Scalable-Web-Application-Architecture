# Verification Report

**Scope:** local, static and database-integration verification of the repository. **No AWS API call, `terraform plan`, `apply` or `destroy` was run.** Results below are what was actually executed in the working copy (2026-10-15).

## Executed – PASS

| Check | Command / method | Result |
|---|---|---|
| Unit + contract tests | `pytest -q` (Python 3.11 and 3.12) | **60 passed** on each (51 app/DB-layer/infra-contract + 9 DB integration; the 9 skip when no database is configured) |
| DB integration (real engine) | `TEST_DB_HOST=127.0.0.1 pytest tests/test_db_integration.py` against MariaDB 10.11 (CI uses `mysql:8.4`) | 9 passed: schema/seed idempotent, concurrent init safe, parameterized reads/writes, order total from stored price, unknown product rejected, **credential rotation recovered**, wrong credentials fail closed with a generic error |
| Stability | full suite repeated 25× | 25/25 green after the schema-init race fix (see below) |
| Lint | `ruff check .` | All checks passed |
| Dependency audit | `pip-audit --disable-pip --no-deps -r requirements.txt` (Python 3.11 pins) | No known vulnerabilities |
| Hygiene | `scripts/check-repository-hygiene.py` | No secret patterns, state files, plans or conflict markers |
| Workflows | `actionlint` 1.7.12 + YAML parse | clean |
| Terraform formatting | `tofu fmt -check -recursive terraform` (OpenTofu, same HCL formatter) | clean |
| User-data size | rendered payload gzip | 15,593 B of the 16,384 B EC2 limit; test fails above 15,700 B |
| UI | headless Chromium screenshots (desktop, mobile, order placed, status) | rendered correctly; mobile nav fixed |
| Checkov (advisory) | `checkov 3.2.432 --framework terraform` | 227 passed / 41 failed; failures are cost/scope trade-offs (cross-region replication, ALB access logs, KMS on log groups, Multi-AZ in dev…) |

## NOT executed (be explicit)

| Item | Why |
|---|---|
| `terraform init` / `validate` / `plan` | Terraform registry and releases hosts are blocked in the sandbox. Run `terraform fmt/validate` in CI and a **plan for the target environment** before any apply |
| `terraform apply` / `destroy` | Not authorised; never run |
| Real AWS behaviour | EC2 bootstrap on Amazon Linux 2023 (`python3.11` + venv assumption), Secrets Manager read via instance role, RDS TLS to the real endpoint, ALB health checks, WAF |
| GitHub Actions execution | Workflows are linted, not run |
| Git history secret scan with `gitleaks`/`trufflehog` | Tools unavailable; only the pattern scan above |
| Load/scale tests | No deployed environment; **no performance numbers are claimed** |

## Defects found by this verification (and fixed)

| Defect | Found by | Fix |
|---|---|---|
| Concurrent seeding by several workers/instances caused sporadic deadlocks (`DatabaseUnavailable`) | repeated runs of `test_concurrent_schema_initialisation_is_safe` | `GET_LOCK('nimbus_schema_init')` around schema + seed |
| user-data exceeded the 16 KB limit (≈19–20 KB) | size measurement | slimmer app, gzip + base64 delivery, guard test |
| Vulnerable `urllib3` on Python 3.9 | `pip-audit` | runtime moved to Python 3.11, dependencies repinned |
| Wrong Terraform state key in CI | analysis of the failed apply log | fixed key + empty-state and destroy guards |

## Expected Terraform impact (not a plan result)

For an existing `dev` stack with correct state: updates to the Launch Template (new user-data, new inline IAM policy on the instance role), an ASG instance refresh, and optionally an RDS parameter group; **no resource should be destroyed**. If the plan shows IAM roles, VPC or RDS being *created*, the state is wrong: stop and use the runbook in `docs/CI-CD.md`.
