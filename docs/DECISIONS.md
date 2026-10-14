# Architecture Decisions

This is a portfolio project meant to be explainable in an interview, not an enterprise system. Every decision below is tied to that goal: keep it simple to operate, and keep the reasoning visible.

## 1. ALB in public subnets, EC2 in private subnets

The ALB sits in the public subnets and accepts HTTP (and HTTPS once a certificate is configured). The application instances sit in private subnets with no public IP, so the ALB is the only entry point. This reduces the attack surface: even a misconfigured security group cannot make an instance reachable without a public route to it.

## 2. Auto Scaling Group across two Availability Zones

The application runs on a minimum of two instances in production, one per AZ, behind the ALB. The ASG uses a Launch Template and instance refresh, so a change to the AMI or user data rolls out as a gradual replacement instead of manual EC2 surgery.

## 3. RDS MySQL, private, Multi-AZ in prod

The database sits in its own private subnets and is reachable only from the application security group on port 3306. Production uses Multi-AZ; dev uses single-AZ to save cost. Multi-AZ improves availability through automatic failover — it does not replace backups.

## 4. A small Flask app instead of PHP

The sample application is a small Flask app in `terraform/modules/compute/app-src/app.py`, served by Gunicorn behind Nginx. It keeps the same two routes (`/`, `/health`) without adding containers or microservices.

## 5. Secrets and SSM

RDS generates and manages its master password in AWS Secrets Manager. The
current sample Flask app only demonstrates the web/application tier and does
not query RDS. Therefore, the EC2 instance role intentionally has
`AmazonSSMManagedInstanceCore` only; it does not retrieve or store an unused
RDS credential. This avoids placing a master credential on an application
host that has no database feature. If database-backed application behavior is
added later, introduce a dedicated least-privilege database user, grant access
to only the required secret, and test connection handling before deployment.
No password is stored in Git, Terraform variables, or user-data source code.

## 6. AMI auto-discovery, with an explicit-pin option

**Problem:** An earlier version required the user to look up an AMI ID by hand (Console or AWS CLI) and paste it into `terraform.tfvars` before any deploy — an unnecessary manual step.

**Cause:** `ami_id` was a required variable with no default in either environment.

**Decision:** Read AWS's own public SSM parameter for the latest Amazon Linux 2023 build (`/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64`) via `data "aws_ssm_parameter"`. `ami_id` is now optional (`default = null`); when left unset the discovered value is used, and when set explicitly it takes priority (`coalesce`).

**Why:** It removes a manual setup step on the first deploy while keeping the option to pin a specific AMI once controlling the exact timing of an update matters. Pinning matters because a "latest" data source can change between two `terraform plan` runs and alter the Launch Template; the `instance_refresh` block already in `modules/compute` is what safely rolls that change out as a gradual replacement, whether the change came from the data source or from an explicit pin.

**Where:** `terraform/modules/compute/main.tf` (the data source and `local.resolved_ami_id`), `terraform/environments/{dev,prod}/variables.tf` (the variable is now optional).

**Result:** A first deploy needs no manual AMI lookup, while an explicit pin stays available and documented for production when timing control is needed (see `docs/OPERATIONS.md`).

## 7. Only the monitoring that is actually needed

The project uses CloudWatch alarms, SNS, and CloudTrail. CloudWatch Synthetics, GuardDuty, and Security Hub were left out — they add cost and more advanced security surface area than this portfolio needs. They can be added later against a real requirement.

## 8. Deletion protection

The state bucket and RDS both have deletion protection enabled. Dev's RDS is the one exception, since dev is meant to be rebuilt freely. Before any `terraform destroy`, read the plan and review the affected resources.

## 9. Remote state storage and locking

Each environment uses a separate S3 backend key (`dev/terraform.tfstate` and `prod/terraform.tfstate`) inside the one bucket that `terraform/bootstrap` creates once. Locking uses S3's native locking feature (`use_lockfile = true`, Terraform >= 1.10) instead of a separate DynamoDB table — one fewer moving part. No real bucket name is committed to Git; the actual value is supplied through a local, gitignored `backend.hcl`.

## 10. Existing resources and import

The original environment was built by hand through the Console. When Terraform is pointed at an account that already has real resources under the same names (an existing RDS or ALB, for example), the correct tool is `terraform import` to bring that resource under management — not assuming Terraform will "discover" it automatically. Import is a one-time action, not part of the normal `plan`/`apply` flow; the steps live in `docs/OPERATIONS.md` rather than here.

## 11. Services kept out of scope

No domain, Route 53, or ACM certificate is required today. No CloudFront, Kubernetes, ECS, automatic AWS deployment pipeline, or multi-region setup. A GitHub Actions CI workflow runs local tests, Terraform validation, and an advisory security scan; it does not apply infrastructure. These boundaries keep cost and complexity down for this portfolio project.

## 12. One NAT Gateway per AZ in production

A single NAT Gateway shared by both AZs would make instances in one AZ depend on the NAT sitting in the other AZ for outbound traffic — an AZ issue could take down outbound connectivity for both AZs, not just the one affected. Production runs one NAT Gateway per AZ so each AZ is self-contained. Dev uses a single shared NAT Gateway to cut cost, an accepted trade-off since dev carries no real traffic (`nat_gateway_count` in `terraform/modules/networking/variables.tf`).

## 13. WAF rate limiting is approximate, not exact

The WAF rate-based rule blocks an IP after it crosses `waf_rate_limit_per_5min` requests, evaluated over a rolling five-minute window. This is a coarse defense against floods and scanners — it is not a precise per-second rate limiter, and it is not a substitute for a CDN or a dedicated bot-management service.

## 14. IAM scope on the state bucket, and no AWS deployment role yet

The bootstrap state bucket currently denies insecure (non-HTTPS) access; it is not yet scoped to a specific operator role or AWS deployment identity. The GitHub Actions workflow added for this repository performs tests and static validation only: it has no AWS credentials, OIDC trust, or permission to apply infrastructure. If AWS deployment automation is introduced later, create a dedicated OIDC role with least-privilege permissions and narrow the state-bucket policy to that role plus the individual operators who need it. Until then, state-bucket operator access remains a documented hardening item.
