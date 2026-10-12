# Change Summary

## Implemented

- Added four focused Flask tests using Flask's test client.
- Improved `app.py` by removing unused imports, centralizing metadata paths, using UTF-8 reads, and logging filesystem fallbacks without exposing secrets.
- Added pinned development dependencies in `requirements-dev.txt`.
- Added Ruff and pytest configuration in `pyproject.toml`.
- Upgraded Flask from 3.1.0 to 3.1.3 after `pip-audit` identified two known vulnerabilities.
- Added a credential-free repository hygiene scanner.
- Added `.github/workflows/ci.yml` for Python, Terraform, dependency, and hygiene checks.
- Added a separate manual `.github/workflows/terraform-deploy.yml` using OIDC and protected GitHub Environments; it does not run on ordinary pushes or pull requests.
- Added `docs/CI-CD.md` with local Linux/WSL and PowerShell commands, workflow behavior, OIDC prerequisites, and evidence boundaries.
- Updated the root README so CI/CD documentation matches the delivered workflows and explicitly keeps Route 53 outside scope.
- Added this verification report and change summary.
- Updated `.gitignore` to cover all `.venv*` directories.
- Independently corrected stale architecture and decision-record statements about CI/CD.
- Added `.pytest_cache/` and `.ruff_cache/` exclusions after observing those generated directories locally.
- Excluded the supplied AI instruction file from the public release archive.

## Deliberately not changed

- The existing AWS three-tier architecture, Terraform module boundaries, historical diagrams, screenshots, and manual validation narrative were preserved.
- No Docker, Kubernetes, ECS migration, database application logic, Route 53, or real AWS deployment was introduced.
- No remote Git branch was pushed, force-updated, or rewritten.

## Manual setup still required

1. Push the release contents to the intended GitHub repository after review.
2. Enable branch protection as appropriate and inspect the first CI run.
3. For optional deployment, configure AWS IAM OIDC, a least-privilege role, and protected GitHub Environments.
4. Set `AWS_DEPLOY_ROLE_ARN`, `AWS_REGION`, `TF_STATE_BUCKET`, and `TF_STATE_KEY_PREFIX` as protected Environment variables.
5. Review every Terraform plan before selecting the manual apply option.
6. Confirm SNS subscriptions and clean up lab resources to avoid unexpected charges.
