# Terraform

This directory codifies the production-inspired architecture described in the root [`README.md`](../README.md) and [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md). It was built after the environment was first deployed manually through the AWS Console, so it represents that architecture rather than claiming that every Terraform-managed resource has already been deployed and tested in a real account.

## Layout

```text
terraform/
├── bootstrap/            # Creates the S3 state bucket and one account-level monthly budget.
├── environments/
│   ├── dev/               # Low-cost settings: 1 NAT, single-AZ RDS, no default cert.
│   └── prod/               # Multi-AZ, 2 NAT Gateways, deletion protection on.
└── modules/
    ├── networking/        # VPC, subnets, IGW, NAT, route tables, Flow Logs
    ├── security/          # Security groups (ALB → App → DB)
    ├── alb/               # ALB, target group, HTTP/HTTPS listeners
    ├── waf/               # Web ACL, ALB association, logging
    ├── compute/           # AMI discovery, IAM, launch template, ASG, app source
    ├── database/          # RDS, subnet group, enhanced monitoring role
    ├── monitoring/        # CloudWatch alarms + SNS
    └── security-services/ # CloudTrail + its S3 bucket
```

`environments/dev` and `environments/prod` call the exact same modules; only the variable values differ. A change to how a component is built belongs in `modules/`; a change to a per-environment value belongs in `environments/<env>/variables.tf` or a local `terraform.tfvars`.

## Remote state and backend

Both environments use an S3 backend with native state locking (`use_lockfile = true`, Terraform >= 1.10 — no DynamoDB table). The bucket is created once by `bootstrap/` and shared by both environments under different state keys. The real bucket name is never committed: it is supplied through a local, gitignored `backend.hcl` (copy it from the matching `backend.hcl.example`).

The bootstrap state also manages one account-level monthly AWS Budget. It defaults to a USD 5 limit and creates 80% forecasted and 100% actual email alerts only when `budget_email` is supplied through `TF_VAR_budget_email` or a local, gitignored tfvars file. Because AWS Budgets are account-level, do not duplicate this resource in the `dev` and `prod` states.

## Variables

Every variable has a sensible default except two, which are required on purpose:

| Variable | Environment | Why no default |
|---|---|---|
| `db_instance_class` | prod | Forces a deliberate size choice instead of silently picking one |
| `alarm_email` (recommended) | prod | Without a subscriber, alarms fire but reach nobody |

Everything else — CIDRs, instance type, ASG limits, NAT Gateway count, `ami_id`, `certificate_arn`, WAF rate limit — has a working default and only needs to change when the default doesn't fit. See each environment's `terraform.tfvars.example`.

The compute module enables CPU target tracking by default. It targets 60% average ASG CPU, scales only within `asg_min_size` and `asg_max_size`, and can be disabled with `enable_cpu_scaling = false`. A load test is still required to prove the behavior in a deployed account.

## Outputs

Each environment exposes `alb_dns_name`, `vpc_id`, `asg_name`, `db_instance_id`, `rds_master_secret_arn` (sensitive — an ARN, not the secret value), `cloudtrail_bucket`, and `sns_topic_arn`.

## Deployment workflow

```bash
terraform fmt -recursive
terraform init -backend-config=".\backend.hcl"
terraform validate
terraform plan
terraform apply
```

Before applying bootstrap, review the account-wide budget limit and optionally set `TF_VAR_budget_email` for alerts.

To remove an environment:

```bash
terraform plan -destroy
terraform destroy
```

Always confirm the AWS account, region, and environment (`dev` vs `prod`) before `apply` or `destroy` — the backend key is per-environment, but the AWS credentials in your shell are not.

Full step-by-step deployment, AMI handling, testing the app, RDS failover/PITR procedures, and load testing live in [`../docs/OPERATIONS.md`](../docs/OPERATIONS.md).

## Validation

```bash
python3 -m py_compile modules/compute/app-src/app.py
terraform fmt -check -recursive .
(cd environments/dev  && terraform init -backend=false && terraform validate)
(cd environments/prod && terraform init -backend=false && terraform validate)
```

## Troubleshooting

Problems actually met while building this (state locking, AMI references, RDS storage constraints, service quotas, interrupted runs, existing-resource imports) are written up in [`../docs/TROUBLESHOOTING.md`](../docs/TROUBLESHOOTING.md).
