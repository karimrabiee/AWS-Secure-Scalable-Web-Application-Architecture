# Test results and evidence

The single reference for what was run, what the results were, and what is **not** proven. This is a self-review by the repository owner, not an independent audit.

Evidence classes used across the repository:

| Class | Meaning |
|---|---|
| **Verified** | Executed locally on 2026-10-20 (commands below), or confirmed by reading the code |
| **Documented** | Owner-supplied screenshot or log, not independently reproduced |
| **Historical** | From the original manual Console build; does not prove the Terraform stack |
| **Not recorded** | Reported as run by the owner, but no log or screenshot is archived here, so no result is claimed |
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
| IaC scan (advisory) | `checkov -d terraform --framework terraform` 3.2.432 | 229 passed / 39 advisory findings, 82 resources, 0 parse errors (classified in section 5) |
| Git-history pattern scan | regex scan of commit history for `AKIA…`, secret-key and private-key patterns | only the regexes inside `scripts/check-repository-hygiene.py` matched; a dedicated scanner (gitleaks/trufflehog) was not run |
| Markdown links | script resolving every relative link in every `*.md` | no broken links |
| user-data size | included in `tests/test_infra_contracts.py` | about 15.6 KB of the 16 KB EC2 limit; the test fails above 15,700 B |

What the 60 tests cover: 51 without a database (Flask routes, validation, security headers, DB layer with a fake connection, static contracts over Terraform and user-data) and 9 against a real engine (idempotent schema and seed, safe concurrent init, parameterised queries, server-side order totals, recovery after a credential change).

These checks prove code and configuration validity. They do not prove AWS runtime behaviour, failover, availability or the effectiveness of any security control.

## 2. Terraform dev stack (Documented)

| Evidence | What it shows | Class |
|---|---|---|
| [`validation-tests/github-actions-deploy20-ci21-2026-10-20.png`](../validation-tests/github-actions-deploy20-ci21-2026-10-20.png) | **CI #21** (commit `aca5482`) and **Terraform deploy (manual) #20** both green. Deploy #20 log excerpt supplied by the owner: apply `0 added, 2 changed, 0 destroyed`; smoke-test attempts 1-5 returned 502 while new instances bootstrapped, attempt 7 returned `/health` 200 and `/ready` 200. The screenshot does not show which commit deploy #20 ran. | Documented |
| [Terraform deploy (manual) #21](https://github.com/karimrabiee/AWS-Secure-Scalable-Web-Application-Architecture/actions/runs/40077713267) | Run summary page opened during review: `workflow_dispatch` on `main` @ `bb3c343`, started 2026-10-24 08:21 UTC, **Success**, 12 m 3 s (Plan 39 s, Apply 11 m 18 s), one artifact `terraform-plan-dev`. Job logs need a GitHub sign-in and were not read. This is the deploy the validation run in section 3 was performed on. | Verified (summary page) |
| [`validation-tests/live-dev-app-home-2026-10-20.png`](../validation-tests/live-dev-app-home-2026-10-20.png) | `dev` ALB serving Nimbus Store, database tier **Connected**, instance in `us-east-1b` | Documented |
| [`validation-tests/live-dev-app-status-2026-10-20.png`](../validation-tests/live-dev-app-status-2026-10-20.png) | `/status`: tiers Healthy, database Connected, MySQL 8.4.8, Python 3.11.16, instance in `us-east-1a`; 337.9 ms is a single query-latency sample, not a benchmark. The image contains a Snipping Tool notification and is kept unedited. | Documented |

Limits: deploy #20 was an in-place update of an existing stack, not a from-scratch deployment. The two screenshots show one instance each, in different Availability Zones. A screenshot is dated evidence, not proof of continuous availability. The other hosted run URLs (CI #21 and deploy #20) are listed in the repository README as owner-supplied references; they were not re-checked during this review. Deploy #21 is the exception (section 3).

The 502 in an earlier run (#18) was never diagnosed from instance logs. The suspected cause (`curl` vs `curl-minimal` on Amazon Linux 2023) is an inference; commit `aca5482` makes user-data check for `curl`, and the later passing smoke test supports it.

## 3. Terraform `dev` validation run (Documented, 2026-10-24)

Owner-run validation of the Terraform-built `dev` stack on 2026-10-24, one session, torn down afterwards. Commands ran from PowerShell with AWS CLI v2, output captured with `Tee-Object` (converted to UTF-8 before archiving); Console screenshots were taken straight after each group of commands. Logs are in [`validation-tests/terraform-dev/logs/`](../validation-tests/terraform-dev/logs/), screenshots in [`validation-tests/terraform-dev/screenshots/`](../validation-tests/terraform-dev/screenshots/). The procedure is in [`OPERATIONS.md`](OPERATIONS.md) section 15.

| Field | Value |
|---|---|
| Region | `us-east-1` |
| Environment | `dev`: 1 NAT Gateway, `db.t3.micro` single-AZ MySQL 8.4.8, ASG `Dev-ASG` min 2 / max 4 (`t3.micro`) |
| Deployed by | Terraform deploy (manual) #21, commit `bb3c343` (section 2) |
| Fresh deploy? | Very likely. The ASG creation time (08:32 UTC) and the RDS instance certificate issue time (about 08:25 UTC) both fall inside the run window (08:21 to about 08:33 UTC). This is an inference from timestamps, not a statement in the job log. |
| Sensitive data | Account ID blacked out in the screenshot that contained it; alert e-mail replaced by `<ALERT_EMAIL>` in the log; a screenshot that showed the tester's public IP was left out of the repository |

### Results

| ID | Test | Expected | Actual | Status | Evidence |
|---|---|---|---|---|---|
| T04 | App reachable through the ALB | HTTP 200 | HTTP 200; storefront and `/status` served, database tier **Connected** | ✅ Pass | [log](../validation-tests/terraform-dev/logs/T04-alb-http.txt) · [AZ b](../validation-tests/terraform-dev/screenshots/T04-app-home-us-east-1b.png) · [AZ a](../validation-tests/terraform-dev/screenshots/T04-app-home-us-east-1a.png) |
| T04 | Orders handled by both AZs | Both instances serve and write to RDS | Orders #6-#9 on `/status` were handled alternately by `i-087c…` (us-east-1a) and `i-07d5…` (us-east-1b); the counter showed 10 products / 9 orders | ✅ Pass | [screenshot](../validation-tests/terraform-dev/screenshots/T04-status-orders-both-azs.png) |
| T05 | Targets healthy | All targets healthy | 2 of 2 healthy, one per AZ | ✅ Pass | [log](../validation-tests/terraform-dev/logs/T05-target-health.txt) · [screenshot](../validation-tests/terraform-dev/screenshots/T05-targets-healthy.png) |
| T06 | No public IP, IMDSv2 required | `PublicIpAddress` None, `HttpTokens` required | Both instances: None / required | ✅ Pass | [log](../validation-tests/terraform-dev/logs/T06-instances.txt) · [ASG screenshot](../validation-tests/terraform-dev/screenshots/T06-asg-instances.png) |
| T07 | RDS private and encrypted | Not public, encrypted | `PubliclyAccessible=False`, `StorageEncrypted=True`, `MultiAZ=False` (intended in `dev`), backup retention 1 day | ✅ Pass | [log](../validation-tests/terraform-dev/logs/T07-rds.txt) · [config](../validation-tests/terraform-dev/screenshots/T07-rds-configuration.png) · [connectivity](../validation-tests/terraform-dev/screenshots/T07-rds-connectivity.png) |
| T08 | No port 22 anywhere in the VPC | No rule on 22 | No security group in the VPC has an ingress rule starting at port 22. A second query listing internet-facing ingress returned a single rule, TCP 80 (the group's name was not captured in the log). | ✅ Pass | [T08](../validation-tests/terraform-dev/logs/T08-no-port22.txt) · [T08b](../validation-tests/terraform-dev/logs/T08b-open-ingress.txt) |
| T09 | WAF: normal request | 200 | 200 | ✅ Pass | [log](../validation-tests/terraform-dev/logs/T09-waf-normal.txt) |
| T10 | WAF: XSS in query string | 403 | 403 | ✅ Pass | [log](../validation-tests/terraform-dev/logs/T10-waf-xss.txt) · [WAF summary](../validation-tests/terraform-dev/screenshots/T10-waf-summary.png) |
| T11 | WAF: `sqlmap/1.0` user agent | Actual result recorded | 403 (blocked) | ✅ Observed | [log](../validation-tests/terraform-dev/logs/T11-waf-badua.txt) |
| T12 | Egress goes through NAT | Public address that is not the instance's | `checkip.amazonaws.com` returned `54.160.141.159` from inside a private instance with no public IP. The NAT Gateway's Elastic IP was not captured next to it, so this is consistent with NAT egress rather than a side-by-side match. | ⚠️ Partial | [screenshot](../validation-tests/terraform-dev/screenshots/T12-T14-ssm-nat-imds.png) |
| T13 | IMDSv2 enforced | 401 without a token | 401 | ✅ Pass | same screenshot |
| T14 | IMDSv2 works with a token | Instance ID | `i-07d5bc222e5a69911` | ✅ Pass | same screenshot |
| T15 | Instance role is least-privilege | `AccessDenied` | `s3:ListAllMyBuckets` and `secretsmanager:ListSecrets` both denied for `ecomm-platform-dev-ec2-ssm-role` | ✅ Pass | [screenshot](../validation-tests/terraform-dev/screenshots/T15-ssm-access-denied.png) |
| T16 | `mysql` client from the instance to RDS | `SELECT VERSION()` succeeds | The archived screenshot ends during the package install and does **not** show the query result. The application itself reached RDS with the Secrets Manager credential: `/status` shows MySQL 8.4.8, TLS 1.3 cipher and orders written. | ⚠️ Partial | [`/status`](../validation-tests/terraform-dev/screenshots/T04-status-orders-both-azs.png) |
| T19 | Alarms exist and notify | Alarms present, SNS subscription confirmed | 9 alarms listed (the 7 Terraform-defined plus 2 target-tracking alarms the ASG policy creates). The SNS subscription was still `PendingConfirmation` and the alarm actions carried a console **Warning**, so e-mail delivery was **not** verified. | ⚠️ Not verified | [SNS log](../validation-tests/terraform-dev/logs/T19-sns-subscription.txt) · [alarms 1](../validation-tests/terraform-dev/screenshots/T19-alarms-1.png) · [alarms 2](../validation-tests/terraform-dev/screenshots/T19-alarms-2.png) |
| n/a | RDS Multi-AZ failover, one NAT Gateway per AZ | prod only | `dev` is single-AZ with one NAT by design | ➖ N/A in `dev` | Failover evidence is historical, from the manual build (section 4) |

WAF: the Web ACL summary shows 36 requests in the window, 34 allowed and 2 blocked, which matches the two blocked requests above. The screenshot of sampled requests showed only allowed requests and also displayed the tester's IP address, so it is not archived; which managed rule matched each blocked request was therefore **not captured**. No block percentage is claimed.

### Run but not recorded

These were planned for the same session. No log or screenshot is archived for them, so this repository makes no claim about their results.

| ID | Test |
|---|---|
| T01-T03 | `fmt`/`validate`, idempotency (`plan -detailed-exitcode`), drift detection (CI runs `fmt` and `validate`; section 1) |
| T17 | Self-healing: terminate one instance, ALB keeps serving, ASG replaces it |
| T18 | Scale-out under CPU load (target tracking at 60% average CPU) |
| T20-T21 | Alarm notification path and a real unhealthy-target alarm (blocked by the unconfirmed SNS subscription above) |
| T22-T24 | CloudTrail `StartSession` / `TerminateInstances` events; VPC Flow Logs `REJECT` query |
| T25-T26 | `terraform destroy` and the leftover-resource checks (the owner reports the stack was destroyed after the session; the output was not archived) |

### Deviations and limits

- Single session, single run. Nothing here is a repeatability or performance claim; the three query latencies seen on `/status` (240.2 ms on the first request, then 23.9 ms and 15.8 ms) are individual samples.
- The Console shows times in UTC+03:00 in some screenshots; logs and the app's order times are UTC.
- A screenshot proves a state at one moment, and the stack no longer exists.

## 4. Original manual build (Historical)

| Evidence | Shows |
|---|---|
| [`validation-tests/RDS-Failover-Successfully-tested.png`](../validation-tests/RDS-Failover-Successfully-tested.png) | RDS Multi-AZ failover completed in under a minute |
| [`validation-tests/WAF-XSS-requests-blocked.png`](../validation-tests/WAF-XSS-requests-blocked.png) | WAF blocked 539 of 699 XSS test requests |
| [`validation-tests/SNS-Email-notifications.png`](../validation-tests/SNS-Email-notifications.png), [`Systems-Manager-Managed-instances-visible.png`](../validation-tests/Systems-Manager-Managed-instances-visible.png), [`CloudTrail-Management-events-logged.png`](../validation-tests/CloudTrail-Management-events-logged.png), [`VPC-Flow-Logs-Traffic-logs-collected.png`](../validation-tests/VPC-Flow-Logs-Traffic-logs-collected.png) | SNS alert email, SSM-managed instances, CloudTrail management events, VPC Flow Logs |
| [`screenshots/01-vpc.png` … `11-cloudwatch-alarm.png`](../screenshots) | Console build steps: VPC, subnets, security groups, ALB, target group, ASG, RDS, WAF, CloudWatch |

These describe the manual build only. No failover or load test has been recorded on the Terraform stack; the WAF checks on it are in section 3.

## 5. Checkov findings (39, advisory)

Run with `--framework terraform`; advisory, not gating in CI.

| Group | Findings |
|---|---|
| Cost / scope trade-offs | S3 cross-region replication, access logging and event notifications; RDS Performance Insights and Multi-AZ in dev; ALB deletion protection and access logs; one-year log retention; KMS on log groups |
| Known design limitations | HTTP listener and ALB-to-HTTP (CKV_AWS_2/103/378, CKV2_AWS_20); ALB ingress 80 from the internet (CKV_AWS_260); RDS IAM authentication (CKV_AWS_161); CloudTrail CloudWatch/SNS/CMK integration (CKV2_AWS_10, CKV_AWS_252, CKV_AWS_35) |
| Likely false positives | CKV2_AWS_28 (the WAF association exists in `modules/waf/main.tf`); CKV2_AWS_5 (security groups attached via module outputs); CKV_AWS_130 (public subnets intentionally assign public IPs for ALB/NAT) |
| Worth a future ticket | default security group restriction (CKV2_AWS_12), security-group descriptions (CKV_AWS_23), RDS minor-version auto-upgrade (CKV_AWS_226), SNS topic encryption (CKV_AWS_26) |

## 6. Not done

| Item | Note |
|---|---|
| `prod` deploy | Not deployed; its cost is mainly RDS Multi-AZ and one NAT Gateway per AZ |
| RDS Multi-AZ failover on the Terraform stack | Needs `prod`; the only failover evidence is the historical manual build |
| Load test (`load-testing/k6-script.js`) on the Terraform stack | No performance figure is claimed anywhere |
| Self-healing, scale-out, alarm e-mail delivery, CloudTrail and Flow Logs queries, teardown output | See "Run but not recorded" in section 3 |
| `terraform init/validate/plan` in the 2026-10-20 local review sandbox | Registry hosts were not reachable there; CI runs `fmt` and `validate` |
| MySQL 8.4 integration run locally | Local engine was MariaDB; MySQL 8.4 runs in CI only |
| HTTPS | Needs an ACM certificate supplied by the user |
| Secret rotation on the live stack | Recovery is tested with a real database in `tests/test_db_integration.py`, not on AWS |
| GuardDuty, Security Hub, AWS Config, customer-managed KMS keys | Not implemented |

## 7. Reproduce locally

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
