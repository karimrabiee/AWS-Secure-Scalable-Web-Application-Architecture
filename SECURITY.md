# Security Policy

This is a personal portfolio project, not a supported product. Reports are still welcome.

## Reporting a vulnerability

Please open a private security advisory on GitHub (**Security → Report a vulnerability**) rather than a public issue. Include the file, what you observed and how to reproduce it. Do not include real credentials.

## What is in scope

Code and infrastructure definitions in this repository (Terraform, the Nimbus Store application, GitHub workflows).

## Known, documented limitations

HTTP-only ALB by default, the application using the RDS master credential, and advisory Checkov findings are documented in [`docs/TEST-RESULTS.md`](docs/TEST-RESULTS.md) and [`docs/SECURITY-CONTROL.md`](docs/SECURITY-CONTROL.md).

## Handling secrets

Never commit `*.tfstate`, `*.tfvars`, `backend.hcl`, plans or credentials. `scripts/check-repository-hygiene.py` runs in CI to catch common patterns.
