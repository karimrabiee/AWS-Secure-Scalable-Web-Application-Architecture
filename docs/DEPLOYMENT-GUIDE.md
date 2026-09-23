# Deployment guide

Step-by-step instructions to build this architecture manually through the AWS Console. Every setting here matches the deployed and validated version of this project.

All resources are in `us-east-1`. Set a billing alert before starting — NAT Gateways and RDS bill hourly.

---

## Phase 0 — Prerequisites

- Log in as an IAM user with administrator permissions (not root).
- In AWS Budgets, create a monthly budget with an email alert at $10.
- Set default region to `us-east-1` in the console.

---

## Phase 1 — VPC

| Setting | Value |
|---|---|
| Name | `Production-VPC` |
| IPv4 CIDR | `10.0.0.0/16` |
| DNS resolution | Enabled |
| Tenancy | Default |

---

## Phase 2 — Subnets

Create all six subnets before moving on.

| Name | CIDR | AZ | Type |
|---|---|---|---|
| Public-Subnet-A | 10.0.1.0/24 | us-east-1a | Public |
| Public-Subnet-B | 10.0.2.0/24 | us-east-1b | Public |
| App-Private-A | 10.0.11.0/24 | us-east-1a | Private (EC2) |
| App-Private-B | 10.0.12.0/24 | us-east-1b | Private (EC2) |
| DB-Private-A | 10.0.21.0/24 | us-east-1a | Private (RDS) |
| DB-Private-B | 10.0.22.0/24 | us-east-1b | Private (RDS) |

Enable **Auto-assign public IPv4** on the two public subnets only.

---

## Phase 3 — Internet Gateway

Create `Production-IGW`. Attach to `Production-VPC`.

---

## Phase 4 — NAT Gateways

Create one NAT Gateway per public subnet. Each needs a new Elastic IP.

| Name | Subnet |
|---|---|
| NAT-A | Public-Subnet-A |
| NAT-B | Public-Subnet-B |

Wait for both to show **Available** before creating route tables.

---

## Phase 5 — Route Tables

| Route table | Subnets | Route |
|---|---|---|
| `public-rt` | Public-Subnet-A, Public-Subnet-B | `0.0.0.0/0` → IGW |
| `private-rt` | App-Private-A, App-Private-B, DB-Private-A, DB-Private-B | `0.0.0.0/0` → NAT per AZ |

> For full AZ independence, create two separate private route tables — one pointing to NAT-A for the us-east-1a subnets, one pointing to NAT-B for us-east-1b. The deployed version uses a single `private-rt` for simplicity; split it for production.

---

## Phase 6 — Security Groups

Create all three before adding rules, then reference by group ID.

**ALB-SG**

| Direction | Port | Source |
|---|---|---|
| Inbound | 80 | 0.0.0.0/0 |
| Inbound | 443 | 0.0.0.0/0 |
| Outbound | All | 0.0.0.0/0 |

**EC2-SG**

| Direction | Port | Source |
|---|---|---|
| Inbound | 80 | ALB-SG |
| Outbound | All | 0.0.0.0/0 |

No SSH rule. Access is via Systems Manager Session Manager only.

**RDS-SG**

| Direction | Port | Source |
|---|---|---|
| Inbound | 3306 | EC2-SG |
| Outbound | All | 0.0.0.0/0 |

---

## Phase 7 — IAM Role for Systems Manager

- Trusted entity: EC2
- Policy: `AmazonSSMManagedInstanceCore`
- Role name: `Production-EC2-SSM-Role`

This is what lets SSM Fleet Manager see and connect to the instances without any open inbound port.

---

## Phase 8 — RDS MySQL

**Create DB subnet group first:**
- Name: `production-db-subnet-group`
- Subnets: DB-Private-A and DB-Private-B

**Create RDS instance:**

| Setting | Value |
|---|---|
| Engine | MySQL 8.4.8 |
| Template | Production |
| Deployment | Multi-AZ DB instance |
| Identifier | `production-db` |
| Instance class | `db.m7g.large` |
| Storage | 20 GiB, gp3 |
| IOPS | 3000 |
| Throughput | 125 MiB/s |
| Storage autoscaling | Enabled, max 1000 GiB |
| Encryption | Enabled (aws/rds) |
| VPC | Production-VPC |
| Subnet group | `production-db-subnet-group` |
| Security group | RDS-SG |
| Public access | No |
| Backup retention | 7 days |
| Performance Insights | Enabled |
| Enhanced Monitoring | Enabled, 60s |
| CloudWatch logs | Audit log |

RDS takes 5–10 minutes to become available.

---

## Phase 9 — EC2 Launch Template

| Setting | Value |
|---|---|
| Name | `Production-LT` |
| AMI | Amazon Linux 2023 (latest) |
| Instance type | `t3.micro` |
| Key pair | None (SSM access only) |
| Security group | EC2-SG |
| IAM instance profile | `Production-EC2-SSM-Role` |

**User data** — the full script is in [`scripts/user-data.sh`](../scripts/user-data.sh). It installs Apache, starts it on boot, and reports the instance's Availability Zone using the IMDSv2 token-based metadata API. This makes AZ-failure testing easy to verify: just refresh the page and check which AZ is answering.

---

## Phase 10 — Target Group and ALB

**Target group:**
- Name: `Production-TG`
- Protocol: HTTP, Port 80
- Health check path: `/`
- Healthy threshold: 2, Unhealthy: 3, Interval: 30s

**ALB:**
- Name: `Production-ALB`
- Scheme: Internet-facing
- Subnets: Public-Subnet-A, Public-Subnet-B
- Security group: ALB-SG
- Listener: HTTP:80 → forward to Production-TG

---

## Phase 11 — Auto Scaling Group

| Setting | Value |
|---|---|
| Name | `Production-ASG` |
| Launch template | `Production-LT` |
| Subnets | App-Private-A, App-Private-B |
| Load balancer | Attach to Production-TG |
| Health check type | ELB |
| Health check grace period | 60 seconds |
| Min / Desired / Max | 2 / 2 / 4 |

---

## Phase 12 — AWS WAF

In the ALB console, choose **Integrate with AWS WAF** to create a Web ACL attached to the ALB automatically.

Add these three managed rule groups:

| Rule | WCU |
|---|---|
| `AWSManagedRulesCommonRuleSet` | 700 |
| `AWSManagedRulesKnownBadInputsRuleSet` | 200 |
| `AWSManagedRulesAmazonIpReputationList` | 25 |

Start in **Count** mode for 30 minutes. Review sampled requests in the WAF console. If no false positives, switch to **Block** mode.

---

## Phase 13 — VPC Flow Logs

- Create CloudWatch Logs group: `/aws/vpc/production-flow-logs`, retention 30 days
- Enable Flow Logs on the VPC: filter All, destination CloudWatch Logs

---

## Phase 14 — CloudTrail, CloudWatch, SNS

**CloudTrail:**
- Create S3 bucket: `production-audit-logs-<account-id>`, block all public access
- Create trail: `Production-Trail`, multi-region, log file validation enabled

**SNS:**
- Topic: `Production-Alerts`, Standard
- Subscription: Email → your address. Confirm the subscription email.

**CloudWatch alarms:**

| Alarm | Metric | Threshold |
|---|---|---|
| `EC2-HighCPU` | EC2 CPUUtilization by ASG | > 70% for 5 min |
| `ALB-Unhealthy-Targets` | ALB UnHealthyHostCount | > 0 for 1 min |

Both alarms → SNS `Production-Alerts`.

---

## Phase 15 — Validation

Run the 7 tests documented in the [README validation section](../README.md#validation-tests) before considering the project complete.
