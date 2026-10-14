# CI/CD and Repository Readiness

This repository uses a deliberately small separation between **CI validation** and **CD deployment**.

## Continuous integration

`.github/workflows/ci.yml` runs on pull requests and pushes to `main`. It does not need AWS credentials and never runs `terraform apply` or `terraform destroy`.

The workflow checks:

1. Python dependencies, `ruff check`, syntax compilation, and pytest on Python 3.9 and 3.12; Python 3.9 is included because it matches the supported Amazon Linux runtime.
2. Terraform formatting for the complete `terraform/` tree.
3. Backend-free `terraform init` and `terraform validate` for `bootstrap`, `environments/dev`, and `environments/prod`.
4. A lightweight repository-hygiene scan for common credentials and private keys.
5. A dependency audit of the application requirements where the package index is available.

The Terraform jobs use `-backend=false`, so CI cannot access or modify the configured S3 state backend.

## Optional CD

`.github/workflows/terraform-deploy.yml` is an intentionally gated, manual workflow (`workflow_dispatch`). It is not triggered by ordinary pushes or pull requests.

Before using it, an owner must:

- Configure an AWS IAM OIDC provider for GitHub Actions.
- Create a dedicated role with least-privilege Terraform permissions and a trust policy restricted to the intended repository and branch/environment.
- Add `AWS_DEPLOY_ROLE_ARN` as a GitHub **Environment variable**.
- Add `AWS_REGION`, `TF_STATE_BUCKET`, and `TF_STATE_KEY_PREFIX` as protected
  GitHub Environment variables. The state bucket must already exist and the
  key prefix must be unique to this repository.
- For `prod`, add `TF_DB_INSTANCE_CLASS` because the Terraform variable is
  deliberately required and has no default. `TF_ALARM_EMAIL` is optional.
- Configure `dev` or `prod` GitHub Environments to match the workflow input; add required reviewers for `prod`.
- Do not use a committed `backend.hcl`; the workflow passes the protected
  backend variables directly to Terraform.

The workflow performs validation and a plan first. Apply is a separate job, protected by the selected GitHub Environment. OIDC uses the `sts.amazonaws.com` audience, AWS identity is printed for account verification, and a per-environment concurrency lock prevents overlapping Terraform runs. This repository does not claim that the optional workflow has been exercised against a real AWS account.

## Local checks

Linux/macOS/WSL:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r terraform/modules/compute/app-src/requirements.txt -r requirements-dev.txt
python -m pytest
ruff check .
python -m py_compile terraform/modules/compute/app-src/app.py
python scripts/check-repository-hygiene.py

terraform fmt -check -recursive terraform
for root in terraform/bootstrap terraform/environments/dev terraform/environments/prod; do
  (cd "$root" && terraform init -backend=false && terraform validate)
done
```

PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r terraform/modules/compute/app-src/requirements.txt -r requirements-dev.txt
python -m pytest
ruff check .
python scripts/check-repository-hygiene.py
terraform fmt -check -recursive terraform
```

The final Terraform validation commands are the same as above, using `Set-Location` for each root.

## Evidence boundary

Passing local tests proves application behavior and Terraform configuration validity only. It does not prove AWS permissions, resource quotas, provider-side behavior, live failover, cost, or a successful deployment. Those require a separately authorized AWS account test and recorded evidence.
