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
