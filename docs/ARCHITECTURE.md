# Architecture

A detailed description of what Terraform builds. The quick summary is in [`README.md`](../README.md); the reasoning behind each choice is in [`DECISIONS.md`](DECISIONS.md).

## Traffic flow

```text
Internet
    │
    ▼
AWS WAF  (Common + KnownBadInputs + AmazonIpReputation + rate limit)
    │
    ▼
Application Load Balancer  (public subnets, across AZ-A and AZ-B)
    │
    ├── AZ-A ── EC2 (App-Private-A) ──┐
    │                                  ├── RDS MySQL (Multi-AZ in prod)
    └── AZ-B ── EC2 (App-Private-B) ──┘
                    │
              NAT Gateway (one per AZ in prod, one shared in dev)

Observability: VPC Flow Logs → CloudWatch Logs
               CloudWatch Alarms → SNS → Email
               CloudTrail → S3 (encrypted, blocked from public access)
Access: SSM Session Manager only - no SSH, no open port 22. The EC2 role also has `secretsmanager:GetSecretValue` scoped to the exact RDS master-secret ARN.
```

## Network

| Tier | Subnets | Internet access | Reachable from |
|---|---|---|---|
| Public | 2 (one per AZ) | Direct via IGW | WAF + ALB only |
| App-private | 2 (one per AZ) | Outbound only, via NAT | ALB security group, port 80 |
| DB-private | 2 (one per AZ) | None | App security group, port 3306 |

Security group chain: `ALB-SG ← 0.0.0.0/0` (80 always, 443 once a certificate exists) → `App-SG ← ALB-SG only` → `DB-SG ← App-SG only`. No rule past the ALB references a raw CIDR.

## AWS services actually used

| Service | Purpose |
|---|---|
| VPC + IGW + 1-2 NAT Gateways | Isolated network across AZ-A and AZ-B |
| AWS WAF (WAFv2) | Blocks common OWASP attacks, known bad inputs, and IPs with poor reputation, plus rate limiting |
| Application Load Balancer | HTTP/HTTPS distribution across AZs, health check on `/health` |
| EC2 + Auto Scaling Group | Application tier; CPU target tracking by default, plus instance refresh when the AMI or user data changes |
| RDS MySQL | Managed database, encrypted, automated backups, Multi-AZ in prod |
| IAM + SSM | Least-privilege EC2 role (SSM plus one exact-ARN secret read), no SSH |
| Secrets Manager | RDS master password, created and rotated by RDS itself, never a Terraform variable |
| CloudWatch + SNS | 7 alarms (EC2 CPU, ALB unhealthy targets, ALB 5xx, ALB p95 latency, RDS CPU/storage/connections) plus email alerting |
| CloudTrail | Management-event logging to a private S3 bucket using SSE-KMS and log-file validation |
| VPC Flow Logs | Network traffic records sent to CloudWatch Logs |
| S3 | Terraform state (separate bucket) and CloudTrail logs |

No Route 53, no mandatory ACM, no CloudFront, no ECS/EKS, no CI/CD in this project — a deliberate choice, see `DECISIONS.md`.

## High availability

| Component | Mechanism |
|---|---|
| ALB | Spans AZ-A and AZ-B, routes only to healthy targets |
| EC2 | Auto Scaling Group with a minimum of two instances (prod), one per AZ, plus CPU target tracking within the configured min/max limits |
| RDS | Multi-AZ in prod — synchronous standby with automatic failover |
| NAT | One per AZ in prod — one AZ's issue does not cut outbound traffic for the other |

## dev vs. prod

Exactly the same modules; only the variables differ:

| Variable | dev | prod |
|---|---|---|
| NAT Gateways | 1 | 2 |
| RDS Multi-AZ | No | Yes |
| RDS instance class | `db.t3.micro` | Set explicitly, no default |
| Deletion protection | Off | On |
| Backup retention | 1 day | 7 days (default, configurable up to 35) |
