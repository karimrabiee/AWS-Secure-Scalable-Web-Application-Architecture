# AWS Secure & Highly Available 3-Tier Web Application

<div align="center">

[![AWS](https://img.shields.io/badge/AWS-us--east--1-FF9900?style=flat-square&logo=amazonaws&logoColor=white)](https://aws.amazon.com/)
[![Terraform](https://img.shields.io/badge/Terraform-%3E%3D1.10-5C4EE5?style=flat-square&logo=terraform&logoColor=white)](https://www.terraform.io/)
[![RDS](https://img.shields.io/badge/RDS-MySQL_Multi--AZ-527FFF?style=flat-square&logo=amazonaws&logoColor=white)](https://aws.amazon.com/rds/)
[![WAF](https://img.shields.io/badge/WAF-Managed_Rules-DD344C?style=flat-square&logo=amazonaws&logoColor=white)](https://aws.amazon.com/waf/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)
[![CI](https://github.com/karimrabiee/AWS-Secure-Scalable-Web-Application-Architecture/actions/workflows/ci.yml/badge.svg)](https://github.com/karimrabiee/AWS-Secure-Scalable-Web-Application-Architecture/actions/workflows/ci.yml)
[![Terraform deploy (manual)](https://github.com/karimrabiee/AWS-Secure-Scalable-Web-Application-Architecture/actions/workflows/terraform-deploy.yml/badge.svg)](https://github.com/karimrabiee/AWS-Secure-Scalable-Web-Application-Architecture/actions/workflows/terraform-deploy.yml)

</div>

## Summary

> A database-backed web application on private AWS infrastructure: designed, built by hand in the AWS Console, validated against failure conditions, then migrated to Terraform and delivered through a guarded GitHub Actions pipeline that authenticates with OIDC. It is a **portfolio project, production-inspired and not independently audited**.

## Project lifecycle

Design → Manual AWS Build → Failure-Condition Validation → Terraform Migration → CI/CD Delivery (OIDC) → Reproducible Infrastructure

| Phase | What was done | Evidence |
|---|---|---|
| Design | Three-tier layout across two AZs | [Initial diagram](architecture/initial-architecture-diagram.png) |
| Manual AWS Build | Built through the Console | [`docs/DEPLOYMENT-GUIDE.md`](docs/DEPLOYMENT-GUIDE.md), [`screenshots/`](screenshots) |
| Failure-Condition Validation | RDS failover under 1 minute, WAF blocked 539 of 699 XSS test requests, SNS, SSM, Flow Logs, CloudTrail (**manual build only**) | [`validation-tests/`](validation-tests) |
| Terraform Migration | 8 modules, separate `dev` / `prod`, S3 remote state with native locking | [`terraform/`](terraform) |
| CI/CD Delivery (OIDC) | `ci.yml` (ruff, pytest 60 tests, `terraform validate`, advisory Checkov, …); `terraform-deploy.yml` (OIDC, saved plan, approval, guards, smoke test) | [`docs/CI-CD.md`](docs/CI-CD.md) |
| Reproducible Infrastructure | `dev` deployed through the pipeline (deploy #20, in-place update); a recorded from-scratch rebuild is a planned next step | [`docs/TEST-RESULTS.md`](docs/TEST-RESULTS.md) |

## At a glance

- **Problem:** serve an app with private servers and database, no SSH, and a rebuildable environment.
- **Stack:** WAF, ALB, EC2 Auto Scaling, RDS MySQL, Secrets Manager, SSM, CloudWatch/SNS, CloudTrail, VPC Flow Logs, Terraform, GitHub Actions (OIDC), Flask + Gunicorn + Nginx.
- **Skills shown:** VPC design, security groups, IAM least privilege, Terraform modules and remote state, CI/CD with OIDC, troubleshooting from real logs.
- **Built by me:** the manual build and its failure tests, the Terraform modules, the pipeline, and the fixes in [`docs/FINDINGS-AND-FIXES.md`](docs/FINDINGS-AND-FIXES.md).
- **Evidence:** [`docs/TEST-RESULTS.md`](docs/TEST-RESULTS.md), [`terraform/`](terraform), [`tests/`](tests), [`.github/workflows/`](.github/workflows).

## The problem

Run a web application where only the load balancer is public, servers and database sit in private subnets across two Availability Zones, administration needs no SSH, and the whole environment can be rebuilt from code.

## Architecture

**Current (Terraform + CI/CD):** WAF → ALB → EC2 Auto Scaling in private subnets → RDS MySQL in private DB subnets, with Secrets Manager, CloudWatch/SNS, CloudTrail and VPC Flow Logs.

![Current architecture](architecture/architecture-diagram.png)

The diagram shows the intended architecture. The `dev` environment has been deployed through the pipeline; see [Evidence and limitations](#evidence-and-limitations) for the verified scope. `dev` runs one NAT Gateway and single-AZ RDS; `prod` runs one NAT Gateway per AZ and Multi-AZ RDS (primary plus standby).

**Initial (manual build):** the first design, kept unchanged.

![Initial architecture](architecture/initial-architecture-diagram.png)

## Running project

| Storefront | Platform status |
|---|---|
| ![Live storefront](validation-tests/live-dev-app-home-2026-10-20.png) | ![Live status page](validation-tests/live-dev-app-status-2026-10-20.png) |

Terraform-built `dev` environment, 2026-10-20. Owner-supplied screenshots (one instance each: `us-east-1b` and `us-east-1a`).

![GitHub Actions: CI #21 and deploy #20](validation-tests/github-actions-deploy20-ci21-2026-10-20.png)

<details>
<summary>Manual-build screenshots (historical)</summary>

[VPC](screenshots/01-vpc.png) · [Subnets](screenshots/02-subnets.png) · [Security groups](screenshots/03-security-groups.png) · [ALB](screenshots/04-alb.png) · [Target group](screenshots/05-target-group.png) · [Auto Scaling](screenshots/06-auto-scaling.png) · [RDS](screenshots/07-rds.png) · [WAF](screenshots/09-waf.png) · [CloudWatch dashboard](screenshots/10-cloudwatch-dashboard.png) · [CloudWatch alarm](screenshots/11-cloudwatch-alarm.png) · [RDS failover](validation-tests/RDS-Failover-Successfully-tested.png) · [WAF XSS blocked](validation-tests/WAF-XSS-requests-blocked.png) · [SNS email](validation-tests/SNS-Email-notifications.png) · [Systems Manager](validation-tests/Systems-Manager-Managed-instances-visible.png) · [CloudTrail](validation-tests/CloudTrail-Management-events-logged.png) · [VPC Flow Logs](validation-tests/VPC-Flow-Logs-Traffic-logs-collected.png)

</details>

## Key design choices and security

| Choice | Detail | Details in |
|---|---|---|
| Private subnets | Only the ALB is public; EC2 and RDS have no public IP | [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Security-group chaining | ALB-SG → App-SG → DB-SG, no raw CIDR past the ALB | [`SECURITY-CONTROL.md`](docs/SECURITY-CONTROL.md) |
| SSM instead of SSH | No port 22; access via Session Manager | [`SECURITY-CONTROL.md`](docs/SECURITY-CONTROL.md) |
| IMDSv2 | Required, hop limit 1 | [`SECURITY-CONTROL.md`](docs/SECURITY-CONTROL.md) |
| Secrets Manager | RDS-managed master password; the EC2 role can read one secret ARN | [`DECISIONS.md`](docs/DECISIONS.md) |
| WAF | AWS managed rules plus a rate-based rule | [`SECURITY-CONTROL.md`](docs/SECURITY-CONTROL.md) |
| Multi-AZ in prod | Multi-AZ RDS and one NAT per AZ in `prod`; `dev` is single-AZ, one NAT | [`DECISIONS.md`](docs/DECISIONS.md) |
| OIDC for CI/CD | No stored AWS keys; saved plan applied only after approval | [`CI-CD.md`](docs/CI-CD.md) |
| Remote state | S3 with native locking (`use_lockfile`), key `ecomm-platform/<env>/terraform.tfstate` | [`DECISIONS.md`](docs/DECISIONS.md) |
| Monitoring and audit | 7 CloudWatch alarms with SNS, CloudTrail management events, VPC Flow Logs | [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) |

## Evidence and limitations

| Claim | Status | Reference |
|---|---|---|
| 60 tests pass on Python 3.11 and 3.12 (51 without a DB, 9 need a database) | Verified locally 2026-10-20 | [`docs/TEST-RESULTS.md`](docs/TEST-RESULTS.md) |
| 7 CloudWatch alarms defined | Verified in code | [`terraform/modules/monitoring/main.tf`](terraform/modules/monitoring/main.tf) |
| CI #21 and Terraform deploy #20 passed; `/health` and `/ready` returned 200 on `dev` | Documented: run links and screenshot supplied by the owner, not re-checked here | [CI #21](https://github.com/karimrabiee/AWS-Secure-Scalable-Web-Application-Architecture/actions/runs/39423145695) · [Terraform deploy #20](https://github.com/karimrabiee/AWS-Secure-Scalable-Web-Application-Architecture/actions/runs/39423190369) · [screenshot](validation-tests/github-actions-deploy20-ci21-2026-10-20.png) |
| App serves from `dev` with the database connected | Documented (dated screenshots) | [`validation-tests/`](validation-tests) |
| RDS failover under 1 minute; WAF 539/699 blocked | Historical (manual build only) | [`validation-tests/`](validation-tests) |
| Failover, WAF and load tests on the Terraform stack | Not done | [`docs/TEST-RESULTS.md`](docs/TEST-RESULTS.md) |
| From-scratch deploy of the Terraform stack | Not done (deploy #20 was an in-place update) | [`docs/TEST-RESULTS.md`](docs/TEST-RESULTS.md) |
| HTTP by default; HTTPS needs your ACM `certificate_arn` | Limitation | [`docs/SECURITY-CONTROL.md`](docs/SECURITY-CONTROL.md) |
| App connects as the RDS master user | Limitation | [`docs/DECISIONS.md`](docs/DECISIONS.md) |
| Checkov (advisory): 229 passed / 39 findings, classified | Verified locally | [`docs/TEST-RESULTS.md`](docs/TEST-RESULTS.md) |
| GuardDuty, Security Hub, AWS Config, customer-managed KMS keys | Not implemented | — |

## Quick start

Needs an AWS account, Terraform 1.10+ and the AWS CLI. For the pipeline, also a GitHub OIDC role ([`docs/iam/README.md`](docs/iam/README.md)).

```bash
cd terraform/bootstrap && terraform init && terraform apply     # state bucket, once
cd ../environments/dev
cp terraform.tfvars.example terraform.tfvars
cp backend.hcl.example backend.hcl
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

Or run **Actions → Terraform deploy (manual)**, choose `dev`, review the plan and approve. Tests: `pip install -r requirements-dev.txt && pytest -q`.

More: [`terraform/README.md`](terraform/README.md) · [`docs/OPERATIONS.md`](docs/OPERATIONS.md)

## Documentation

| Doc | Purpose |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | What Terraform builds |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Why each choice |
| [`docs/SECURITY-CONTROL.md`](docs/SECURITY-CONTROL.md) | Security controls and limits |
| [`docs/CI-CD.md`](docs/CI-CD.md) | Workflows, OIDC, guards |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | Deploy, test, teardown |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | Errors met and fixes |
| [`docs/TEST-RESULTS.md`](docs/TEST-RESULTS.md) | Tests and evidence |
| [`docs/COST-ANALYSIS.md`](docs/COST-ANALYSIS.md) | Cost estimates |
| [`docs/README.md`](docs/README.md) | Full index |

## Cost and cleanup

NAT Gateways, RDS, ALB and WAF are billed by the hour while they exist. Use `dev` (one NAT, single-AZ RDS), set a budget alert, and destroy when finished. Teardown is manual only: `terraform plan -destroy`, then `terraform destroy` ([`docs/OPERATIONS.md`](docs/OPERATIONS.md) §14). Figures in [`docs/COST-ANALYSIS.md`](docs/COST-ANALYSIS.md) are estimates from mid-2025 prices.

## Author

**Karim Rabie**

Junior Cloud Engineer | AWS | Terraform | Docker | K8s | CI/CD | Cloud Infrastructure

[LinkedIn](https://www.linkedin.com/in/karim-rabiee) · [GitHub](https://github.com/karimrabiee) · MIT licence ([`LICENSE`](LICENSE))

