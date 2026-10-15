# CV Bullets (evidence-based)

Use only claims backed by `docs/VERIFICATION-REPORT.md`. Do not add latency/throughput/uptime numbers unless you measure them on a deployed environment.

- Designed and codified a secure three-tier AWS architecture (ALB + WAF, private EC2 Auto Scaling, Multi-AZ-capable RDS MySQL) as modular Terraform with isolated dev/prod environments and S3 remote state with native locking.
- Diagnosed a failing GitHub Actions deployment to a **Terraform state-key mismatch** (resources re-created against an empty state) and fixed it with a fixed backend key, empty-state and destructive-plan guards, saved-plan apply behind environment approval, and concurrency control.
- Built a database-backed Flask/Gunicorn/Nginx application reading RDS credentials from AWS Secrets Manager at runtime, with TLS host verification, parameterized queries, bounded timeouts and automatic recovery from credential rotation.
- Wrote **60 automated tests** (Python 3.11 and 3.12), including real-database integration tests in CI (`mysql:8.4`), static Terraform contract tests and a user-data size guard (15.6 KB of the 16 KB EC2 limit); suite repeated 25× without failures after fixing a concurrent schema-initialisation race.
- Hardened the delivery pipeline: least-privilege OIDC role (scoped `iam:PassRole`, exact-object state access), `ruff`, `pip-audit` (no known vulnerabilities), `actionlint`, repository secret-hygiene checks and advisory Checkov (227 passed / 41 reviewed findings).
- Validated the original manually built stack with a Multi-AZ RDS failover (<1 min) and WAF XSS blocking (539 of 699 test requests blocked in that run).
