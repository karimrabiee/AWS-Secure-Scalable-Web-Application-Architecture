# AWS Secure & Highly Available 3-Tier Web Application

<div align="center">

[![AWS](https://img.shields.io/badge/AWS-us--east--1-FF9900?style=flat-square&logo=amazonaws&logoColor=white)](https://aws.amazon.com/)
[![Terraform](https://img.shields.io/badge/Terraform-%3E%3D1.10-5C4EE5?style=flat-square&logo=terraform&logoColor=white)](https://www.terraform.io/)
[![RDS](https://img.shields.io/badge/RDS-MySQL_Multi--AZ-527FFF?style=flat-square&logo=amazonaws&logoColor=white)](https://aws.amazon.com/rds/)
[![WAF](https://img.shields.io/badge/WAF-Managed_Rules-DD344C?style=flat-square&logo=amazonaws&logoColor=white)](https://aws.amazon.com/waf/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

</div>

> A production-inspired AWS three-tier web application: secure, highly available, monitored, and codified with Terraform. The architecture was built manually first to validate the design under real failure conditions, then represented as reusable Terraform modules. It is a portfolio implementation, not a claim of an independently audited production service.

**Lifecycle:** Design → Manual AWS Build → Validation → Terraform Migration → Reproducible Infrastructure

---

## The Problem

A web application needs to stay available while keeping its servers and database off the public internet, with controlled access between tiers, no SSH exposure, and infrastructure that can be rebuilt reliably rather than reconstructed by hand.

## The Solution

```text
                         INTERNET
                            |
                            v
                         AWS WAF
                            |
                            v
                           ALB
                         /     \
                        v       v
                  EC2 / ASG   EC2 / ASG
                  Private AZ-A Private AZ-B
                        \       /
                         v     v
                        RDS MySQL
                         Multi-AZ (prod)

       CloudWatch ───► SNS        CloudTrail ───► S3
       Flow Logs  ───► CloudWatch  SSM ─────────► EC2
```

![Architecture Diagram](architecture/architecture-diagram.png)

| Layer | Design |
|---|---|
| Network | VPC across 2 Availability Zones |
| Public entry | ALB + AWS WAF |
| Application | Private EC2, Auto Scaling |
| Database | Private RDS MySQL, Multi-AZ in prod |
| Administration | SSM Session Manager — no SSH |
| Monitoring | CloudWatch + SNS |
| Auditing | CloudTrail + VPC Flow Logs |
| IaC | Terraform, modular, `dev`/`prod` |

## Project Specifications

| | Original validated build | Terraform (`dev` / `prod`) |
|---|---|---|
| Region | `us-east-1` | Variable, defaults `us-east-1` |
| VPC / AZs | `10.0.0.0/16`, 2 AZs, 6 subnets | Same |
| EC2 | `t3.micro`, Amazon Linux 2023 | Same instance type; AMI auto-discovered via SSM Parameter Store (pin optional) |
| Auto Scaling | Min 2 / Desired 2 / Max 4 | Same, configurable |
| RDS | MySQL 8.4.8, `db.m7g.large`, Multi-AZ | MySQL 8.4.8 default; `dev` = `db.t3.micro`, single-AZ; `prod` = instance class required explicitly (no silent default), Multi-AZ |
| RDS storage | 20 GiB gp3, 3,000 IOPS, 125 MiB/s | Same gp3 defaults |
| WAF | 3 managed rule groups | Same, plus a rate-based rule (2,000 req/5 min per IP) |
| Admin access | SSM Session Manager, no SSH | Same |
| Terraform / provider | — | `>= 1.10.0`, AWS provider `>= 5.60.0` |

The left column is what was actually built and load-tested manually (see [Validation](#validation)). `dev` and `prod` are intentionally different, not a copy of each other — see [`docs/DECISIONS.md`](docs/DECISIONS.md).

## Security

```text
Internet → ALB-SG (80, and 443 once a certificate exists, from 0.0.0.0/0)
        → EC2-SG (port 80, from ALB-SG only)
        → RDS-SG (port 3306, from EC2-SG only)
```

Only the ALB accepts public traffic; every rule past it references a security group, never a raw CIDR. The EC2 role combines `AmazonSSMManagedInstanceCore` with one inline `secretsmanager:GetSecretValue` permission scoped to the exact RDS master-secret ARN.

| Control | Status |
|---|---|
| EC2 private, no public IP | ✅ |
| RDS private, no internet route | ✅ |
| No SSH — SSM Session Manager only | ✅ |
| IMDSv2 enforced, hop limit 1 | ✅ |
| IAM least privilege (SSM + one scoped Secrets Manager ARN) | ✅ |
| AWS WAF — managed rules + rate limiting | ✅ |
| RDS encryption at rest, automated backups | ✅ |
| CloudTrail + VPC Flow Logs | ✅ |

AWS WAF uses AWS Managed Rules to help block common web exploits and known-bad traffic — this is threat mitigation, not a guarantee. Full detail: [`docs/SECURITY-CONTROL.md`](docs/SECURITY-CONTROL.md)

## High Availability

| Component | Mechanism |
|---|---|
| ALB | Spans both AZs, routes only to healthy targets |
| EC2 | Auto Scaling Group, one instance per AZ minimum (prod) |
| RDS | Multi-AZ in prod — synchronous standby, automatic failover |
| NAT | One per AZ in prod, so one AZ's issue doesn't affect outbound traffic in the other |

On an AZ failure, the ALB stops routing to it and the ASG attempts a replacement in the healthy AZ, subject to available capacity — this is the design intent, not a guarantee independent of AWS-side conditions. A real Multi-AZ failover was performed during the manual build and completed in under one minute (see [Validation](#validation)).

## Monitoring and Auditing

The Terraform-managed stack defines 7 CloudWatch alarms. All alarms publish to one SNS topic; an email subscription is created only when `alarm_email` is supplied and the recipient confirms the SNS subscription.

| Alarm | Metric |
|---|---|
| EC2 high CPU | `AWS/EC2 CPUUtilization` |
| ALB unhealthy targets | `AWS/ApplicationELB UnHealthyHostCount` |
| ALB 5xx rate | `AWS/ApplicationELB HTTPCode_Target_5XX_Count` |
| ALB p95 latency | `AWS/ApplicationELB TargetResponseTime` |
| RDS high CPU | `AWS/RDS CPUUtilization` |
| RDS low free storage | `AWS/RDS FreeStorageSpace` |
| RDS connection count | `AWS/RDS DatabaseConnections` |

CloudTrail records management events to an encrypted S3 bucket; VPC Flow Logs stream to CloudWatch Logs.

## Terraform

```text
terraform/
├── bootstrap/            # S3 state bucket, run once
├── environments/
│   ├── dev/
│   └── prod/
└── modules/
    ├── networking/  security/  alb/  waf/
    └── compute/     database/  monitoring/  security-services/
```

Reusable modules · `dev`/`prod` separation · encrypted S3 remote state with native S3 locking (`use_lockfile`, no DynamoDB) · Amazon Linux 2023 AMI auto-discovery · input validation · optional HTTPS via `certificate_arn` · RDS deletion protection in prod.

### Quick Start

```bash
cd terraform/bootstrap
terraform init && terraform apply

cd ../environments/dev
cp terraform.tfvars.example terraform.tfvars
cp backend.hcl.example backend.hcl
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

PowerShell: replace `cp` with `Copy-Item`. No domain or ACM certificate is required for the default HTTP deployment. HTTPS can be enabled by providing a valid ACM certificate ARN through `certificate_arn`.

Full workflow, deletion-protection notes, and troubleshooting: [`terraform/README.md`](terraform/README.md)

## Evidence Boundary

The repository contains two different kinds of evidence and they must not be read as interchangeable:

| Evidence | Environment | Meaning |
|---|---|---|
| RDS failover, WAF blocking, SNS, SSM, and Flow Logs screenshots | Original manually built AWS environment | Demonstrates that the design was exercised manually; it does not by itself prove that Terraform recreated the same state. |
| Terraform `fmt`, `init -backend=false`, and `validate` | Repository configuration | Demonstrates that the committed Terraform is syntactically valid and internally consistent without contacting the real backend. |
| Terraform `plan` and `apply` | A real AWS account | Must be executed and recorded separately for each environment before claiming that the Terraform stack is deployed. |
| Load-test scale-out results | Not claimed by default | Must include the actual command, timestamp, environment, ASG capacity change, p95 latency, and cleanup result. |

The project is therefore presented as **production-inspired** until a real AWS deployment and repeatable validation record are attached to the Terraform-managed environment.

## Validation

> Results below are from the original, manually built environment, before the Terraform migration. See [`docs/OPERATIONS.md`](docs/OPERATIONS.md) for running equivalent checks against the Terraform-deployed stack.

| Test | Result |
|---|---|
| RDS Multi-AZ failover | ✅ Completed in under one minute |
| WAF XSS blocking | ✅ 539 of 699 test requests blocked in that run |
| Auto Scaling | ✅ Original manual build maintained desired capacity across both AZs; Terraform adds CPU target tracking but requires a separate load-test run to prove scale-out |
| SNS email alert | ✅ Delivered |
| SSM Session Manager | ✅ No port 22, IAM-authenticated |
| VPC Flow Logs / CloudTrail | ✅ Traffic and management events captured |

![WAF Validation](validation-tests/WAF-XSS-requests-blocked.png)

<details>
<summary><strong>Screenshots — 16 total, every layer</strong></summary>

| | |
|---|---|
| ![VPC](screenshots/01-vpc.png) | ![Subnets](screenshots/02-subnets.png) |
| ![Security Groups](screenshots/03-security-groups.png) | ![WAF](screenshots/09-waf.png) |
| ![ALB](screenshots/04-alb.png) | ![Target Group](screenshots/05-target-group.png) |
| ![Auto Scaling](screenshots/06-auto-scaling.png) | ![Systems Manager](screenshots/13-systems-manager.png) |
| ![RDS](screenshots/07-rds.png) | ![RDS Failover](screenshots/08-rds-failover.png) |
| ![CloudWatch Dashboard](screenshots/10-cloudwatch-dashboard.png) | ![CloudWatch Alarm](screenshots/11-cloudwatch-alarm.png) |
| ![SNS Email](screenshots/12-sns-email.png) | ![CloudTrail](screenshots/14-cloudtrail.png) |
| ![VPC Flow Logs](screenshots/15-vpc-flowlogs.png) | ![Production App](screenshots/production-app.png) |

</details>

## Documentation

| File | Covers |
|---|---|
| [`terraform/README.md`](terraform/README.md) | Terraform workflow and module reference |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Full architecture detail |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Why each design choice was made |
| [`docs/SECURITY-CONTROL.md`](docs/SECURITY-CONTROL.md) | Security design reference |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | Deploying and testing the Terraform stack |
| [`docs/COST-ANALYSIS.md`](docs/COST-ANALYSIS.md) | Cost breakdown and assumptions |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | Issues hit and how they were resolved |
| [`docs/DEPLOYMENT-GUIDE.md`](docs/DEPLOYMENT-GUIDE.md) | Original manual build, phase by phase |
| [`docs/LESSONS-LEARNED.md`](docs/LESSONS-LEARNED.md) | Key takeaways from the migration |

## Cost

Main drivers: RDS, NAT Gateways, ALB, WAF, CloudWatch. `dev` defaults to the cheaper end (1 NAT, single-AZ RDS, `db.t3.micro`); `prod` requires an explicit instance class rather than a silent default. A historical hourly estimate for the original validated configuration is documented in [`docs/COST-ANALYSIS.md`](docs/COST-ANALYSIS.md) — actual AWS pricing varies by region, usage, and time, so treat any number there as a point-in-time estimate, not current pricing. Destroy environments when not in use; NAT Gateways and RDS bill hourly regardless of traffic.

## Future Improvements

HTTPS + Route 53 + ACM · GitHub Actions CI/CD · load testing at higher concurrency · ECS/Fargate migration for the application tier.

## Cleanup

```bash
cd terraform/environments/dev   # or prod
terraform destroy
```

`prod` uses RDS deletion protection. To destroy the production environment, disable deletion protection in the production configuration, apply the change, and then run `terraform destroy`. Destroy the `bootstrap` state bucket only after no environment depends on it anymore.

## License

[MIT](LICENSE)

## Author

**Karim Rabie**

Junior Cloud Engineer | AWS | Terraform | Docker | Cloud Infrastructure

[LinkedIn](https://www.linkedin.com/in/karim-rabiee) · [GitHub](https://github.com/karimrabiee)


