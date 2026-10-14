# End-to-End Audit and Repair Report

**Repository:** `AWS-Secure-Scalable-Web-Application-Architecture`
**Audit date:** 2026-10-14
**Scope:** Source repository and local static validation only. No AWS API calls or infrastructure changes were performed during this repair.

## A. Executive Summary

### Overall status

**Source repaired; local static checks partly verified; AWS and Terraform verification blocked. Not production-ready on the evidence available.**

The most important incident evidence was a Gunicorn worker import failure on an EC2 instance running Python 3.9.25. The deployed `app.py` used `str | Path` without deferred annotation evaluation, raising `TypeError` before the Flask app could serve requests. Nginx remained up and returned 502 because its upstream on `127.0.0.1:8000` was not available.

The supplied repository version did not contain that exact annotation, so the repository and deployed artifact were not identical at the time of the incident. The compute module already embeds `app.py` and the requirements file through `filebase64()` into Launch Template user data, the ASG references `aws_launch_template.app.latest_version`, and instance refresh is enabled by default. The exact AWS-side reason the older code remained on the instance cannot be proven without inspecting the live Launch Template versions, instance launch times, ASG refresh history, and user-data hash.

### Major changes made

- Made the Flask source explicitly compatible with Python 3.9 and added startup preflight checks for import, `/health`, and `/`.
- Pinned the complete observed runtime dependency set.
- Reworked EC2 user data to fail fast, emit useful bootstrap logs, validate Nginx configuration, bound service health retries, and perform end-to-end local health checks.
- Kept application code and its virtual environment root-owned instead of writable by the service account; added systemd hardening and a bounded restart policy.
- Removed an unused RDS master-secret retrieval path and the associated EC2 IAM permission. The sample Flask application does not query RDS, as already stated in the project decision record; copying the master secret onto an app host therefore had no runtime benefit.
- Added Flask behavior tests, source-contract tests, and a GitHub Actions CI workflow that does not deploy or apply infrastructure.
- Updated architecture/security/operations documentation and the architecture image to reflect SSM-only instance permissions.

### Verification boundary

- **Verified locally:** Python source compilation; Bash syntax; source-contract tests; workflow YAML parsing; heuristic secret scan; `git diff --check`.
- **Partly verified locally:** `pytest` completed with six passed and one skipped. The skipped module is the Flask behavioral suite because Flask is not installed in this environment and package installation was blocked by unavailable DNS/network access.
- **Not verified:** Terraform formatting, initialization, validation, Checkov execution, actual Terraform plan, AWS Launch Template version creation, ASG instance refresh, ALB target health, and live HTTP behavior.
- **AWS changes:** None. No `terraform apply`, `destroy`, AWS mutation, or state operation was run.

## B. Modified and Created Files

| File path | Change type | Original problem | Exact modification | Reason | Verification |
|---|---|---|---|---|---|
| `terraform/modules/compute/app-src/app.py` | Modified | Runtime annotation failure was observed on the deployed artifact; metadata read failures were silent | Added `from __future__ import annotations`, used `Union[str, Path]`, explicit UTF-8, and warning logs for filesystem errors; removed unused imports | Python 3.9 compatibility and actionable non-sensitive diagnostics | `py_compile` PASS; Flask behavior tests BLOCKED locally / configured in CI |
| `terraform/modules/compute/app-src/requirements.txt` | Modified | Only direct dependencies were pinned; the deployed artifact had a newer Flask version | Pinned Flask, Gunicorn, and the observed transitive dependency set | More repeatable bootstrap resolution | Not installed locally because PyPI DNS was unavailable |
| `terraform/modules/compute/user-data.sh.tftpl` | Modified | Bootstrap did not validate app import/routes before starting services, emitted weak diagnostics, and fetched an unused RDS master secret | Added bootstrap logging, explicit `curl`, source preflight, Flask test-client checks, root-owned app files, hardened systemd unit, bounded health retries, Nginx proxy timeouts and warning detection; removed `awscli`/`jq` and secret-file handling | Fail early rather than silently run a broken upstream; least privilege; safer service runtime | `bash -n` PASS; rendered AWS behavior NOT RUN |
| `terraform/modules/compute/main.tf` | Modified | EC2 role had a Secrets Manager policy not used by the app | Removed `secretsmanager:GetSecretValue` policy and removed DB values from `templatefile()` arguments; retained `filebase64()` delivery of app and requirements | Remove unused access and keep the template contract minimal | Source-contract tests PASS; Terraform validation BLOCKED |
| `terraform/modules/compute/variables.tf` | Modified | Compute module required unused DB/secret inputs | Removed `db_secret_arn`, `db_address`, and `db_port` inputs | Keep module interface aligned with actual app behavior | Source-contract tests PASS; Terraform validation BLOCKED |
| `terraform/environments/dev/main.tf` | Modified | Passed unused DB secret/address/port/name into compute | Removed the unused compute module arguments; database module remains | Keep the three-tier infrastructure while avoiding unused credential delivery | Source-contract tests PASS; Terraform validation BLOCKED |
| `terraform/environments/prod/main.tf` | Modified | Same unused compute inputs as dev | Removed the unused compute module arguments; database module remains | Keep environment module contracts consistent | Source-contract tests PASS; Terraform validation BLOCKED |
| `docs/DECISIONS.md` | Modified | Described fetching the RDS master password to the app host despite no DB use | Documented SSM-only role and the conditions for adding DB integration later | Security/design record matches implementation | `git diff --check` PASS |
| `docs/SECURITY-CONTROL.md` | Modified | IAM inventory overstated the current app role's permissions | Updated EC2 role and least-privilege descriptions | Accurate control documentation | `git diff --check` PASS |
| `docs/ARCHITECTURE.md` | Modified | Architecture and CI descriptions were stale | Updated IAM and clarified CI-only versus deployment automation | Avoid misleading project claims | `git diff --check` PASS |
| `docs/ARCHITECTURE-EVOLUTION.md` | Modified | Current IAM description was stale | Updated role description and change matrix | Preserve historical context without claiming unused access exists in current code | `git diff --check` PASS |
| `README.md` | Modified | Current role description and future CI description were stale | Updated role and diagram captions; documented the validation workflow and that it does not deploy | Public-facing claims match repository intent | `git diff --check` PASS |
| `docs/OPERATIONS.md` | Modified | No focused runbook for this Nginx/Gunicorn 502 failure mode | Added SSM-based diagnostic commands and source-to-Launch-Template-to-ASG deployment chain | Repeatable incident diagnosis without opening SSH or exposing secrets | `git diff --check` PASS; commands not run against AWS |
| `architecture/architecture-diagram.mmd` | Modified | Diagram source showed an unused Secrets Manager edge from the EC2 role | Removed the secret edge and marked role as SSM-only | Source diagram matches least-privilege implementation | Source reviewed; Mermaid renderer unavailable |
| `architecture/architecture-diagram.png` | Modified | Rendered diagram showed the removed master-secret permission | Updated the Security & Management panel to show SSM-only role and Session Manager | Keep the visible README diagram aligned with the source change | Image inspected visually |
| `tests/test_app.py` | Created | No Flask behavioral tests existed | Added tests for home page, health response, missing/empty metadata, and filesystem errors | Catch application regressions without AWS or RDS | Skipped locally due missing Flask; CI installs dependencies and runs it |
| `tests/test_source_contract.py` | Created | No tests verified template variables, Python compatibility, or the source-to-ASG delivery contract | Added syntax, template argument, no-unused-secret, latest Launch Template version, ASG refresh, and Bash checks | Detect regressions in bootstrap wiring | Six total tests passed across suite; see test results |
| `requirements-dev.txt` | Created | No pinned test dependency declaration existed | Added pinned pytest and reference to pinned runtime requirements | Reproducible local/CI test setup | Not install-tested due no network; current system pytest executed source tests |
| `.github/workflows/ci.yml` | Created | No CI workflow existed | Added Python 3.9/3.12 tests, Terraform fmt/init/validate for bootstrap/dev/prod, and advisory Checkov scan; read-only repo permission; no AWS credentials or apply | Automate repeatable checks without infrastructure mutation | YAML parsed locally; GitHub Actions execution NOT RUN |
| `docs/audit-repair-report.md` | Created | No complete evidence-based audit report existed | This report: findings, file inventory, test evidence, security review, infrastructure impact, blockers, and readiness | Traceable audit record | Report reviewed against actual commands and repository diff |

The pre-existing untracked file `what i need manus do.txt` was preserved and not edited.

## C. Findings and Resolution Matrix

| Finding ID | Severity | Root cause / evidence | Files affected | Resolution | Status |
|---|---|---|---|---|---|
| F-001 | High | EC2 journal showed Gunicorn import failing on `str | Path` with Python 3.9.25; deployed source differed from the supplied repository copy | `app.py`, User Data, compute Launch Template wiring | Python 3.9-safe annotations, import/route preflight, pinned dependencies; source is embedded into User Data and source changes feed Launch Template version | Source repaired; AWS rollout not verified |
| F-002 | High | Nginx returned 502 because no healthy process listened on `127.0.0.1:8000`; `ecomm-app.service` restarted after worker boot failure | User Data, systemd service | Startup preflight, bounded retries, service logs, final checks through Gunicorn and Nginx | Source repaired; AWS behavior not verified |
| F-003 | Medium | User Data fetched RDS master credentials and wrote a file even though the sample app never queried RDS | Compute IAM, User Data, env module calls, docs | Removed unused secret retrieval and EC2 `GetSecretValue` permission; documented DB integration as not implemented | Resolved in source; requires reviewed Terraform plan |
| F-004 | Medium | Application code was recursively owned by the app service user | User Data | App source and venv are root-owned and not group/world writable; app service runs as a dedicated non-login user | Source repaired; systemd behavior not AWS-tested |
| F-005 | Medium | Dependency resolution was not fully pinned and could drift between instance launches | Runtime requirements | Pinned observed direct and transitive runtime packages | Implemented; package install blocked locally |
| F-006 | Medium | No app/source-contract tests or CI workflow existed | Tests, requirements-dev, GitHub workflow | Added behavioral and source-contract tests and validation workflow | Implemented; CI run pending |
| F-007 | Medium | Nginx syntax test can emit a conflicting `server_name` warning without treating that warning as a fatal error | User Data | Bootstrap now detects this warning and fails with an explicit diagnostic rather than proceeding silently | Implemented; Nginx runtime not AWS-tested |
| F-008 | Medium | Documentation and diagram overstated current app-role permissions and CI/CD scope | README, architecture docs/diagram, operations | Updated role description, diagram, 502 runbook, and CI/deployment boundary | Resolved in source |
| F-009 | Medium | No actual Terraform plan/validation could be run in this environment | All Terraform roots/modules | Added CI validation workflow; no claim of Terraform success made | Blocked pending CI/Terraform execution |
| F-010 | Medium | No security scanner was installed and package downloads failed due DNS/network unavailability | CI workflow/report | Added pinned Checkov advisory scan in CI; local scanner result is not claimed | Pending CI execution |
| F-011 | Medium | State bucket policy is documented as denying insecure transport but not restricting principals to a specific operator/deployment role | `terraform/bootstrap/main.tf`, `docs/DECISIONS.md` | Documented as remaining hardening work; no broad policy change made without knowing operator IAM principals | Open / accepted scope limitation |
| F-012 | Medium | Application is a demo page and health endpoint; it does not execute DB queries although RDS infrastructure exists | `app.py`, README and architecture docs | Explicitly documented; no unrequested application redesign or DB feature was added | Open functional limitation |
| F-013 | Medium | HTTP remains the default when `certificate_arn` is null | ALB module and environment variables | Existing optional HTTPS behavior documented; no certificate/domain was invented | Open deployment prerequisite for public production use |
| F-014 | Low | Existing AWS screenshots and manually built infrastructure evidence do not prove the repaired Terraform-managed environment is deployed | Validation evidence/docs | Report distinguishes historical/manual evidence from this source repair | AWS verification required |

## D. Test Results

### Baseline before modifications

| Command | Result | Evidence |
|---|---|---|
| `python3 -m py_compile terraform/modules/compute/app-src/app.py` | PASS | Exit code 0 |
| `pytest -q` | FAIL / no tests | `no tests ran`, exit code 5; confirmed missing test suite |
| `terraform fmt -check -recursive` | BLOCKED | `terraform: command not found`, exit code 127 |
| `git diff --check` | PASS | Exit code 0; baseline had no tracked changes |
| `python3 -m pip install -r terraform/modules/compute/app-src/requirements.txt` | BLOCKED | DNS resolution failed for package index; Flask could not be installed in this environment |

### After modifications

| Command | Result | Evidence / notes |
|---|---|---|
| `python3 -m pytest -q` | PASS with one skip | `6 passed, 1 skipped`; skipped module is Flask behavioral tests because Flask is unavailable locally |
| `python3 -m py_compile terraform/modules/compute/app-src/app.py tests/test_app.py tests/test_source_contract.py` | PASS | Exit code 0 |
| `bash -n terraform/modules/compute/user-data.sh.tftpl` | PASS | Exit code 0; verifies shell syntax, not EC2 execution or Terraform template rendering by Terraform itself |
| `python3` PyYAML parse of `.github/workflows/ci.yml` | PASS | Workflow YAML parsed; PyYAML's YAML 1.1 loader treats `on` as a boolean key, while GitHub Actions uses its supported workflow syntax. CI has not run on GitHub yet |
| Heuristic source/history secret scan | PASS (no matches) | No access-key ID, private-key header, or obvious hardcoded password pattern was detected in scanned repository files or reachable Git history. This is not a substitute for a dedicated secret scanner |
| `git diff --check` | PASS | Exit code 0 after edits |
| `terraform fmt -check -recursive` | BLOCKED | Terraform binary unavailable |
| `terraform init -backend=false` and `terraform validate` for bootstrap/dev/prod | NOT RUN / BLOCKED | Terraform binary unavailable; network restriction prevented installation. CI workflow is configured to run them |
| Checkov | NOT RUN / BLOCKED | Not installed locally; package installation was blocked by network/DNS. CI workflow includes a pinned advisory Checkov scan |
| AWS `terraform plan` | NOT RUN | Deliberately not attempted without Terraform CLI and actual backend configuration; no state or AWS infrastructure was touched |
| AWS target health / Launch Template / ASG refresh | NOT RUN | Requires AWS-side inspection and an authorized plan/apply workflow |

## E. Terraform and Infrastructure Impact

### Expected changes inferred from source (not confirmed by a Terraform plan)

- `aws_launch_template.app` should receive a new version because the content of the application source, requirements, and User Data template changes.
- The ASG references `aws_launch_template.app.latest_version` and has instance refresh enabled by default. A reviewed plan and AWS refresh history are required to confirm whether the fleet will roll as intended.
- The EC2 inline policy `read_db_secret` is removed. The EC2 role retains `AmazonSSMManagedInstanceCore`.
- No RDS, VPC, subnet, ALB, WAF, CloudTrail bucket, or Terraform state resource was intentionally changed by this source patch.

### Risks and cost

- A Launch Template update and ASG instance refresh will replace instances over time, which may incur EC2/NAT data-transfer cost and a short period of reduced capacity. The current refresh settings and actual plan must be reviewed before apply.
- The source-only change is not proof that the running AWS fleet changed. Do not claim the 502 is resolved in AWS until target health and both local/ALB endpoints are verified.
- No plan was generated; therefore exact resources to change/replace/delete, downtime, and cost are **unknown** rather than zero.
- No infrastructure was applied or destroyed, and no state object was modified.

## F. Security Review

- **IAM:** Removed EC2's unused `secretsmanager:GetSecretValue` inline policy. SSM access remains through `AmazonSSMManagedInstanceCore`. This is correct for the current sample app, which does not query RDS.
- **Secrets:** No password is embedded in Terraform variables, User Data, the app, or the report. Removed the unnecessary runtime secret retrieval and local `db.json` file.
- **Network:** Existing intended path remains internet → ALB → app instances, with RDS isolated to its private DB subnets and SG references. No SG rule was weakened or changed in this repair.
- **Instance hardening:** IMDSv2 remains required by the Launch Template. The service runs as non-root; code/venv are root-owned; systemd filesystem/kernel hardening is added.
- **Logging:** Bootstrap writes `/var/log/ecomm-app-bootstrap.log`, systemd/Gunicorn logs to journald, and startup errors are surfaced without shell tracing. Nginx config conflicts now stop bootstrap.
- **State and audit:** Existing S3 backend encryption/locking, CloudTrail, WAF, VPC Flow Logs, and CloudWatch configuration were not changed. The bootstrap state-bucket policy is not yet restricted to an explicit operator role; this remains documented hardening work.
- **Security scanner:** Checkov has been added to CI as an advisory scan but has not executed in this environment. No scanner findings are claimed.
- **Secret scan:** Heuristic source and reachable-history scan found no obvious key/password patterns; a dedicated scanner is still recommended before public release.

## G. Remaining Work and Production Readiness

The project should **not** be labeled production-ready based on this source-only repair. Before production approval:

1. Run the new GitHub Actions workflow and fix any Terraform format/validate or Checkov findings that are confirmed defects.
2. Configure the correct remote backend locally and run `terraform plan` for dev. Review the exact Launch Template/ASG/IAM diff; confirm there are no unexpected database/network replacements.
3. If approved, apply only the reviewed plan, then inspect the ASG instance refresh status and verify all ALB targets become `healthy`.
4. Through SSM, verify Python version, `systemctl status ecomm-app nginx`, `journalctl -u ecomm-app`, `/var/log/ecomm-app-bootstrap.log`, `curl http://127.0.0.1:8000/health`, and `curl http://127.0.0.1/health`.
5. Verify the ALB's `/health` and home page return HTTP 200; check Nginx logs for duplicate `server_name` warnings and confirm no target is returning 502.
6. Decide deliberately whether this project remains a demo app with separate RDS infrastructure or whether database-backed behavior is a requirement. If DB access is added, use a dedicated least-privilege DB user, not the RDS master account, and test connection failures/timeouts.
7. Configure and validate ACM/HTTPS for any public production deployment. HTTP is currently the default if no certificate ARN is provided.
8. Review state-bucket principal restrictions, backup/PITR recovery, alert delivery confirmation, WAF logging/cost, and retention requirements with the actual operator/account context.
9. Review the Python 3.9 runtime lifecycle and decide whether to migrate to a newer supported Python runtime with a tested AMI/package plan. This repair keeps compatibility with the observed runtime rather than introducing an unverified runtime migration.
10. Perform a documented rollback rehearsal and AWS-side operational checks. Existing manual screenshots are not proof of this repaired deployment.

## H. Git Summary

- **Commits created:** No.
- **Pushes performed:** No.
- **AWS changes:** No.
- **Pre-existing untracked user file:** `what i need manus do.txt` retained unchanged.

Actual `git status --short` after the source changes:

```text
 M README.md
 M architecture/architecture-diagram.mmd
 M architecture/architecture-diagram.png
 M docs/ARCHITECTURE-EVOLUTION.md
 M docs/ARCHITECTURE.md
 M docs/DECISIONS.md
 M docs/OPERATIONS.md
 M docs/SECURITY-CONTROL.md
 M terraform/environments/dev/main.tf
 M terraform/environments/prod/main.tf
 M terraform/modules/compute/app-src/app.py
 M terraform/modules/compute/app-src/requirements.txt
 M terraform/modules/compute/main.tf
 M terraform/modules/compute/user-data.sh.tftpl
 M terraform/modules/compute/variables.tf
?? .github/
?? docs/audit-repair-report.md
?? requirements-dev.txt
?? tests/
?? "what i need manus do.txt"
```

Actual `git diff --stat` (tracked files only; untracked files are listed separately above):

```text
 README.md                                          |  12 +-
 architecture/architecture-diagram.mmd              |   5 +-
 architecture/architecture-diagram.png              | Bin 192432 -> 162348 bytes
 docs/ARCHITECTURE-EVOLUTION.md                     |   7 +-
 docs/ARCHITECTURE.md                               |   6 +-
 docs/DECISIONS.md                                  |  22 ++--
 docs/OPERATIONS.md                                 |  36 ++++--
 docs/SECURITY-CONTROL.md                           |   4 +-
 terraform/environments/dev/main.tf                 |   4 -
 terraform/environments/prod/main.tf                |   4 -
 terraform/modules/compute/app-src/app.py           |  15 ++-
 terraform/modules/compute/app-src/requirements.txt |  13 ++-
 terraform/modules/compute/main.tf                  |  19 ----
 terraform/modules/compute/user-data.sh.tftpl       | 125 ++++++++++++++-------
 terraform/modules/compute/variables.tf             |  19 ----
 15 files changed, 162 insertions(+), 129 deletions(-)
```

`git diff --check`: **PASS**, exit code 0. Newly created files remain untracked until the user chooses to commit them. No commit or push was made.

## I. Final Status

**Status: Source-level repair completed with partial local verification. AWS deployment and Terraform validation remain unverified.** The known Python annotation failure is addressed in source, startup now validates the app before the instance is allowed to finish bootstrap, and the unused master-secret path has been removed. The durable AWS outcome still requires a reviewed Terraform plan and authorized rollout followed by target-health verification.
