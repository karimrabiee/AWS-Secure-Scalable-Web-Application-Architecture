# Verification Report

**Repository:** AWS Secure & Highly Available 3-Tier Web Application  
**Verification date:** 2026-10-14  
**Scope:** Local repository validation only; no AWS resources were created or changed.

## Verification matrix

| Check | Command or method | Result | Evidence or explanation | Remaining action |
|---|---|---|---|---|
| Python syntax | `python -m py_compile terraform/modules/compute/app-src/app.py` | PASS | Application compiled successfully. | None for local syntax. |
| Python tests | `pytest -q` | PASS | 4 tests passed: home page, health endpoint, missing metadata, filesystem error fallback. | Run against a deployed EC2 instance only if live behavior evidence is needed. |
| Python lint | `ruff check .` | PASS | Ruff completed with no findings. | None. |
| Dependency audit | `pip-audit -r terraform/modules/compute/app-src/requirements.txt` | PASS | No known vulnerabilities after upgrading Flask to 3.1.3. | Re-run periodically as dependencies change. |
| Repository hygiene | `python scripts/check-repository-hygiene.py` | PASS | No common access-key, private-key, or secret assignment patterns found in release files. | Review any future real credentials immediately and rotate exposed credentials. |
| Git history filename/pattern review | Temporary extraction of supplied `.git`; `git log`, `git ls-tree`, `git grep` | PASS | Recent history was readable; no secret-like tracked filenames or listed high-risk patterns were found at `HEAD`. | A full historical secret scanner is still recommended before publishing if the complete history is retained. |
| YAML workflow syntax | PyYAML parse of `.github/workflows/*.yml` | PASS | Both workflows parsed successfully. | GitHub should run CI after upload; local parsing is not GitHub execution. |
| Terraform formatting | `terraform fmt -check -recursive terraform` | PASS | Terraform 1.10.5 reported no formatting changes. | None. |
| Terraform bootstrap validation | `terraform init -backend=false` then `terraform validate` | PASS | Provider initialized and configuration validated. | Requires an AWS account only for real apply. |
| Terraform dev validation | `terraform init -backend=false` then `terraform validate` | PASS | Modules initialized and configuration validated. | Requires an AWS account only for real apply. |
| Terraform prod validation | `terraform init -backend=false` then `terraform validate` | PASS | Modules initialized and configuration validated. | Requires an AWS account only for real apply. |
| Final rerun after incident repair | `py_compile`, `ruff`, `pytest`, `pip-audit`, YAML parse, Terraform fmt, and backend-free validation for all roots | PASS | 4 tests passed; no dependency vulnerabilities; bootstrap/dev/prod validated with Terraform 1.10.5. | Fresh EC2 rollout and ALB health remain AWS-only checks. |
| GitHub Actions execution | Not available locally | NOT RUN | Workflows were syntax-checked but not executed by GitHub in this environment. | Push the release to a branch and inspect the Actions run. |
| AWS plan/apply | Deliberately not attempted | NOT RUN | No AWS credentials were used and no paid resources were created. | Configure OIDC, protected environments, backend variables, then run the manual workflow only after review. |
| Live failover/load test | Deliberately not attempted | NOT RUN | Existing screenshots remain historical manual-build evidence. | Re-run and record tests against a Terraform-managed environment if required. |
| GitHub Actions static analysis | `actionlint` command availability check | BLOCKED | `actionlint`, Trivy, Gitleaks, Checkov, and ShellCheck are not installed in the sandbox. YAML was still parsed successfully with PyYAML. | Run actionlint and a full secret/IaC scanner in CI or locally before public publication. |

## Important evidence boundary

Successful local validation proves code and configuration consistency. It does **not** prove AWS IAM permissions, quotas, provider-side behavior, network reachability, live WAF behavior, failover, scaling, cost, or production readiness.

## Independent findings and remediation

| Severity | Finding | Evidence and impact | Correction | Verification |
|---|---|---|---|---|
| Medium | Architecture documentation said CI/CD did not exist. | `docs/ARCHITECTURE.md` contradicted the delivered workflows and could confuse reviewers. | Clarified that CI exists, while automatic AWS deployment and several runtime services remain out of scope. | Documentation link scan and text review. |
| Medium | Decision record described CI/CD as intentionally deferred. | `docs/DECISIONS.md` was stale after CI/CD was added. | Updated the decision to describe lightweight CI and optional manual OIDC deployment without changing the AWS runtime architecture. | Documentation text review. |
| Low | `.gitignore` omitted `.pytest_cache/` and `.ruff_cache/`. | Local generated caches were present after validation and could be accidentally committed. | Added recursive cache exclusions. | Final archive scan excludes both cache directories. |
| Low | The supplied instruction file is an AI task artifact, not a public project document. | It is useful for review context but unnecessary and potentially misleading in a public portfolio release. | Excluded `what i need manus do.txt` from the final archive while preserving project documentation. | Final archive content inspection. |
| Medium | The manual CD workflow previously exported optional GitHub variables directly as `TF_VAR_*`, which could pass an empty string and override Terraform defaults in `dev`. | An empty `TF_VAR_db_instance_class` or `TF_VAR_alarm_email` could make a plan fail or create an invalid optional notification. | The workflow now keeps raw deployment variables separate, sets Terraform variables only when needed, and fails early when `prod` lacks `TF_DB_INSTANCE_CLASS`. | YAML parsing, local Terraform validation, and workflow review. |
| Informational | The attached AWS log showed an early `502 Bad Gateway` before the application tier was fully ready. | The later log showed `Apply complete! Resources: 70 added`; the first curl was not sufficient evidence of a Terraform failure. | Added a diagnostic guide: wait for ASG/User Data, inspect Target Group health, then use SSM to check Gunicorn/Nginx/cloud-init. | `docs/E2E-CI-CD-TESTING-AR.md`; live AWS re-test remains external. |
| Critical | Python 3.9 evaluates `str | Path` at import time, causing Gunicorn workers to fail and Nginx/ALB to return 502. | The incident log reported `TypeError: unsupported operand type(s) for |: 'type' and 'type'` during application import. | Replaced the annotation with `typing.Union`, documented the supported runtime, and added Python 3.9 to CI. | Python compile, Flask tests, Ruff, and CI matrix review; a fresh EC2 rollout remains an AWS test. |
| High | Bootstrap could fail before the service was ready because it required optional IMDS data and fetched an unused RDS Secret. | The sample Flask app has no database client or query path, while the deployed instance failed before a healthy port 8000 listener existed. | Added bounded retries, metadata fallbacks, explicit service/health checks, and removed unused secret retrieval plus its EC2 IAM permission. | Terraform validation, template review, local application tests; live User Data execution remains external. |

The current source has no unresolved Critical or High finding from the incident review. Third-party action tags remain versioned major tags rather than invented commit SHAs; pinning to verified SHAs is a follow-up hardening option, not something this review can safely invent.

The two incident findings above are now corrected in source. They should be treated as **fixed locally, pending live AWS rollout verification** until a new Launch Template version is deployed and its targets pass the ALB health check.

## Release hygiene

The release archive excludes `.git`, `.terraform/`, Python virtual environments, bytecode, Terraform state, plans, credentials, and machine-specific files. Terraform provider lock files are retained because they are intentional, reviewable dependency locks.
