# Test results and evidence

The single reference for what was run, what the results were, and what is **not** proven. This is a self-review by the repository owner, not an independent audit.

Evidence classes used across the repository:

| Class | Meaning |
|---|---|
| **Verified** | Executed locally on 2026-10-20 (commands below), or confirmed by reading the code |
| **Documented** | Owner-supplied screenshot or log, not independently reproduced |
| **Historical** | From the original manual Console build; does not prove the Terraform stack |
| **Not done** | Not run; no claim is made |

## 1. Local and static checks (Verified)

Run on 2026-10-20 in a clean checkout of `main` @ `aca5482`, Linux, Python 3.11 and 3.12, MariaDB 10.11 as the local database (CI uses `mysql:8.4`). No AWS credentials were present and no AWS call was made.

| Check | Command | Result |
|---|---|---|
| Tests, no database | `pytest -q` (3.11 and 3.12) | 51 passed, 9 skipped (DB tests skip without `TEST_DB_HOST`) |
| Tests, real database | `TEST_DB_HOST=127.0.0.1 pytest -q` (3.11 and 3.12) | 60 passed |
| Stability | full suite repeated 25x | 25/25 green after fixing a concurrent schema-init race |
| Lint | `ruff check .` | clean |
| Dependency audit | `pip-audit --disable-pip --no-deps -r terraform/modules/compute/app-src/requirements.txt` | no known vulnerabilities |
| Repository hygiene | `python scripts/check-repository-hygiene.py` | no secret patterns, state files, plans or conflict markers |
| Workflow lint | `actionlint` 1.7.12 | clean |
| Terraform format | `tofu fmt -check -recursive terraform` (OpenTofu, same formatter) | clean |
| IaC scan (advisory) | `checkov -d terraform --framework terraform` 3.2.432 | 229 passed / 39 advisory findings, 82 resources, 0 parse errors (classified in section 4) |
| Git-history pattern scan | regex scan of commit history for `AKIA…`, secret-key and private-key patterns | only the regexes inside `scripts/check-repository-hygiene.py` matched; a dedicated scanner (gitleaks/trufflehog) was not run |
| Markdown links | script resolving every relative link in every `*.md` | no broken links |
| user-data size | included in `tests/test_infra_contracts.py` | about 15.6 KB of the 16 KB EC2 limit; the test fails above 15,700 B |

What the 60 tests cover: 51 without a database (Flask routes, validation, security headers, DB layer with a fake connection, static contracts over Terraform and user-data) and 9 against a real engine (idempotent schema and seed, safe concurrent init, parameterised queries, server-side order totals, recovery after a credential change).

These checks prove code and configuration validity. They do not prove AWS runtime behaviour, failover, availability or the effectiveness of any security control.

## 2. Terraform dev stack (Documented)

| Evidence | What it shows | Class |
|---|---|---|
| [`validation-tests/github-actions-deploy20-ci21-2026-10-20.png`](../validation-tests/github-actions-deploy20-ci21-2026-10-20.png) | **CI #21** (commit `aca5482`) and **Terraform deploy (manual) #20** both green. Deploy #20 log excerpt supplied by the owner: apply `0 added, 2 changed, 0 destroyed`; smoke-test attempts 1-5 returned 502 while new instances bootstrapped, attempt 7 returned `/health` 200 and `/ready` 200. The screenshot does not show which commit deploy #20 ran. | Documented |
| [`validation-tests/live-dev-app-home-2026-10-20.png`](../validation-tests/live-dev-app-home-2026-10-20.png) | `dev` ALB serving Nimbus Store, database tier **Connected**, instance in `us-east-1b` | Documented |
| [`validation-tests/live-dev-app-status-2026-10-20.png`](../validation-tests/live-dev-app-status-2026-10-20.png) | `/status`: tiers Healthy, database Connected, MySQL 8.4.8, Python 3.11.16, instance in `us-east-1a`; 337.9 ms is a single query-latency sample, not a benchmark. The image contains a Snipping Tool notification and is kept unedited. | Documented |

Limits: deploy #20 was an in-place update of an existing stack, not a from-scratch deployment. The two screenshots show one instance each, in different Availability Zones. A screenshot is dated evidence, not proof of continuous availability. The hosted run URLs are listed in the repository README as owner-supplied references; they were not re-checked during this review.

The 502 in an earlier run (#18) was never diagnosed from instance logs. The suspected cause (`curl` vs `curl-minimal` on Amazon Linux 2023) is an inference; commit `aca5482` makes user-data check for `curl`, and the later passing smoke test supports it.

## 3. Original manual build (Historical)

| Evidence | Shows |
|---|---|
| [`validation-tests/RDS-Failover-Successfully-tested.png`](../validation-tests/RDS-Failover-Successfully-tested.png) | RDS Multi-AZ failover completed in under a minute |
| [`validation-tests/WAF-XSS-requests-blocked.png`](../validation-tests/WAF-XSS-requests-blocked.png) | WAF blocked 539 of 699 XSS test requests |
| [`validation-tests/SNS-Email-notifications.png`](../validation-tests/SNS-Email-notifications.png), [`Systems-Manager-Managed-instances-visible.png`](../validation-tests/Systems-Manager-Managed-instances-visible.png), [`CloudTrail-Management-events-logged.png`](../validation-tests/CloudTrail-Management-events-logged.png), [`VPC-Flow-Logs-Traffic-logs-collected.png`](../validation-tests/VPC-Flow-Logs-Traffic-logs-collected.png) | SNS alert email, SSM-managed instances, CloudTrail management events, VPC Flow Logs |
| [`screenshots/01-vpc.png` … `11-cloudwatch-alarm.png`](../screenshots) | Console build steps: VPC, subnets, security groups, ALB, target group, ASG, RDS, WAF, CloudWatch |

These describe the manual build only. No failover, WAF or load test has been recorded on the Terraform stack.

## 4. Checkov findings (39, advisory)

Run with `--framework terraform`; advisory, not gating in CI.

| Group | Findings |
|---|---|
| Cost / scope trade-offs | S3 cross-region replication, access logging and event notifications; RDS Performance Insights and Multi-AZ in dev; ALB deletion protection and access logs; one-year log retention; KMS on log groups |
| Known design limitations | HTTP listener and ALB-to-HTTP (CKV_AWS_2/103/378, CKV2_AWS_20); ALB ingress 80 from the internet (CKV_AWS_260); RDS IAM authentication (CKV_AWS_161); CloudTrail CloudWatch/SNS/CMK integration (CKV2_AWS_10, CKV_AWS_252, CKV_AWS_35) |
| Likely false positives | CKV2_AWS_28 (the WAF association exists in `modules/waf/main.tf`); CKV2_AWS_5 (security groups attached via module outputs); CKV_AWS_130 (public subnets intentionally assign public IPs for ALB/NAT) |
| Worth a future ticket | default security group restriction (CKV2_AWS_12), security-group descriptions (CKV_AWS_23), RDS minor-version auto-upgrade (CKV_AWS_226), SNS topic encryption (CKV_AWS_26) |

## 5. Not done

| Item | Note |
|---|---|
| `terraform init/validate/plan` in the local review environment | Registry hosts were not reachable there; CI runs `fmt` and `validate` |
| From-scratch deploy and teardown of the Terraform stack | Planned next step |
| Failover, WAF and load tests (`load-testing/k6-script.js`) on the Terraform stack | No performance figure is claimed anywhere |
| MySQL 8.4 integration run locally | Local engine was MariaDB; MySQL 8.4 runs in CI only (not observed here) |
| HTTPS | Needs an ACM certificate supplied by the user |
| Secret rotation on the live stack | Recovery is tested with a real database in `tests/test_db_integration.py`, not on AWS |
| GuardDuty, Security Hub, AWS Config, customer-managed KMS keys | Not implemented |

## 6. Reproduce locally

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q                                   # 51 passed, 9 skipped
TEST_DB_HOST=127.0.0.1 pytest -q            # 60 passed (local MySQL/MariaDB, root without password)
ruff check .
python scripts/check-repository-hygiene.py
actionlint .github/workflows/*.yml
terraform fmt -check -recursive terraform
checkov -d terraform --framework terraform --quiet --compact
```
