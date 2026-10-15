# Audit and Repair Report

Scope: repository only. No AWS call, no `terraform apply/destroy` was performed. See `VERIFICATION-REPORT.md` for exact results and what was NOT run.

## 1. Root causes

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | `terraform apply` in Actions: `EntityAlreadyExists` (IAM roles), `VpcLimitExceeded` | The workflow used state key `${TF_STATE_KEY_PREFIX}/<env>.tfstate`, different from the key already holding the stack (`ecomm-platform/<env>/terraform.tfstate`). Terraform saw an empty state and tried to create everything again. The SNS topic was created because it did not exist yet | Fixed key; empty-state guard; destroy/replace guard; saved-plan apply; concurrency group; lock timeout |
| 2 | Site "not connected to the database" | The old sample app had no database client at all (and the EC2 role had no secret access) | New database-backed app (PyMySQL, Secrets Manager, TLS, schema + seed, orders), IAM read of one secret ARN, DB endpoint/port/name wired into compute |
| 3 | Site looks unprofessional | Minimal placeholder page | Responsive "Nimbus Store" UI, status page, error pages, accessible markup, strict CSP |
| 4 | Unmerged conflict markers and CRLF noise in source and docs | Bad merge | Resolved; `.gitattributes`; test + hygiene check forbid markers |
| 5 | Python 3.9 runtime pinned vulnerable dependencies | AL2023 default python | `python3.11`, repinned, `pip-audit` clean |

## 2. Changed files (by area)

- **Workflows:** `ci.yml`, `terraform-deploy.yml`.
- **Terraform:** `modules/compute/{main,variables}.tf`, `user-data.sh.tftpl`; `modules/database/{main,variables,outputs}.tf` (opt-in `enforce_tls` parameter group, `copy_tags_to_snapshot`); `modules/alb/main.tf` (`drop_invalid_header_fields`); `environments/{dev,prod}/main.tf`; `bootstrap/main.tf`.
- **Application:** `app-src/{app.py,db.py,requirements.txt,templates/,static/}`.
- **Tests:** `tests/{conftest,test_app,test_db,test_db_integration,test_infra_contracts}.py`; removed `test_source_contract.py`.
- **Tooling/docs:** `pyproject.toml`, `requirements-dev.txt`, `.gitattributes`, `.gitignore`, `scripts/state-inventory.sh`, `docs/iam/*`, README and docs; removed `what i need to do.txt`, `docs/CHANGE-SUMMARY.md`, `docs/E2E-CI-CD-TESTING-AR.md`, stale screenshot.

## 3. Security review

- No secrets, state, plans, tfvars or `backend.hcl` in the tree (pattern scan; history scan with dedicated tools NOT run).
- SQL: parameterized only; LIKE input escaped; order total computed server-side.
- App: JSON-only POST, input validation, CSP and security headers, generic error bodies, no stack traces.
- Instance: IMDSv2, no SSH, root-owned code, hardened systemd unit, secret read limited to one ARN.
- CI role: PassRole constrained, state prefix-scoped, no wildcard admin.
- Accepted limitations: master DB user in the app; HTTP by default; Checkov advisory findings listed in the README.

## 4. Remaining risks / manual steps

1. Run `terraform validate` and a real **plan** for `dev`; confirm no creates for IAM/VPC/RDS and no deletes.
2. Add to the CI role `iam:PutRolePolicy`/`GetRolePolicy`/`DeleteRolePolicy` (and RDS parameter-group actions if `enforce_tls`).
3. Remove the obsolete `TF_STATE_KEY_PREFIX` variable; set `TF_STATE_BUCKET`.
4. After the first apply, check `/ready` through the ALB; if 503, see `docs/OPERATIONS.md` §5.
5. Confirm on a real instance that `python3.11` + `venv` install succeeds on the current AL2023 AMI.
6. Run a dedicated secret scanner over git history before making the repo public.
