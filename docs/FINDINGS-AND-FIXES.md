# Problems found and fixed

Real defects hit while building and delivering the project, with root cause and fix. Evidence for each is in the owner's CI/deploy logs or in the file named in the last column.

| Defect | Root cause | Fix | Evidence |
|---|---|---|---|
| Deploy recreated resources and failed with `EntityAlreadyExists`, `VpcLimitExceeded` | CI used a different state key than the existing state, so Terraform saw an empty state | Fixed per-environment key; empty-state guard; destroy/replace gate; saved-plan apply | Owner logs; `DECISIONS.md` |
| CI failed with `ModuleNotFoundError: render_user_data` | A duplicate second implementation of tests/scripts was merged | Removed (PR #1) | Owner CI logs |
| user-data larger than 16 KB | Embedded app too large | Slimmer app, `base64gzip`, guard test | `tests/test_infra_contracts.py` |
| Sporadic deadlock seeding the database from several workers | Concurrent schema init | `GET_LOCK('nimbus_schema_init', 15)` | 25/25 stability run |
| Vulnerable `urllib3` on Python 3.9 | Old runtime | Python 3.11 runtime, repinned | `pip-audit` clean |
| `HeadObject` 403 on the state object | `s3:ListBucket` carried an `s3:prefix` condition | Unconditional `ListBucket` | `docs/iam/README.md` |
| Later 403s: CloudTrail bucket `GetBucketCORS`, RDS monitoring `PassRole`, WAF `GetWebACLForResource`, WAF logging | Deploy role missing actions | Policy increments | `docs/iam/*` |
| "Saved plan is stale" on apply | Plan was older than the state | Guard behaving as designed; re-run plan then apply | Owner logs |
| 502 Bad Gateway after apply (run #18) | Suspected `curl` package conflict on AL2023 | `aca5482` checks for `curl` | Deploy #20 smoke test passed |
| Alarms showed a console **Warning**; no alert e-mail could arrive | The SNS e-mail subscription stayed `PendingConfirmation` during the validation run (an earlier plan had also wanted to destroy it because the e-mail variable was empty) | Confirm the subscription before any alarm test; added as a pre-flight step in `OPERATIONS.md` section 15 | `validation-tests/terraform-dev/logs/T19-sns-subscription.txt` |
| Evidence screenshot did not contain the result (DB connection test) | The capture was taken while the package install was still running | Re-capture after the command returns; the result is not claimed in `TEST-RESULTS.md` | `docs/TEST-RESULTS.md` section 3 (T16) |
| Archived logs unreadable on GitHub | PowerShell `Tee-Object` writes UTF-16 | Convert to UTF-8 before committing (command in `OPERATIONS.md` section 15) | `validation-tests/terraform-dev/logs/` |
