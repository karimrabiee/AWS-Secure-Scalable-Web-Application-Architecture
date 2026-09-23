# Operations Guide

## Requirements

Terraform `>= 1.10`, the AWS CLI, and AWS credentials with permission to create this project's resources. Never put credentials inside a file in this repository.

## 1. AMI (optional — no manual step required)

Each environment discovers the latest Amazon Linux 2023 AMI automatically through SSM Parameter Store (`data "aws_ssm_parameter"` in `modules/compute`). No manual AMI lookup is needed for a first deploy.

To take explicit control of exactly when the fleet moves to a new AMI (for example, in prod after validating a specific build), pin it in a local `terraform.tfvars`:

```hcl
ami_id = "ami-0123456789abcdef0"
```

The same value can be read manually, only to verify it:

```bash
aws ssm get-parameter \
  --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query Parameter.Value --output text --region us-east-1
```

Changing `ami_id` creates a new Launch Template version, and instances are replaced gradually through `instance_refresh` (`enable_instance_refresh = true` by default) with no manual EC2 work.

## 2. Create the state bucket once

```bash
cd terraform/bootstrap
terraform init
terraform apply
terraform output bucket_name
```

Put the resulting bucket name in each environment's local `backend.hcl`. Never commit the real account ID or bucket name.

## 3. Deploy dev

```bash
cd terraform/environments/dev
cp terraform.tfvars.example terraform.tfvars
cp backend.hcl.example backend.hcl
# Edit backend.hcl locally (bucket name). ami_id is optional — leave it unset.
terraform init -backend-config=".\backend.hcl"
terraform fmt -check -recursive ../../..
terraform validate
terraform plan
terraform apply
terraform output alb_dns_name
```

The app is then reachable at:

```text
http://<alb_dns_name>
```

Leave `certificate_arn = null` when there is no domain and ACM certificate.

## 4. Deploy prod

Prod requires `db_instance_class` in a local `terraform.tfvars` (no default — a deliberate choice, see `docs/DECISIONS.md`). `ami_id` is optional, same as section 1. `certificate_arn` is optional; `null` means HTTP only. Once a domain and a validated ACM certificate exist, put the ARN in the local file and the ALB opens HTTPS and redirects HTTP to it.

```bash
cd terraform/environments/prod
cp terraform.tfvars.example terraform.tfvars
cp backend.hcl.example backend.hcl
# Edit db_instance_class and backend.hcl locally; ami_id and certificate_arn are optional.
terraform init -backend-config=".\backend.hcl"
terraform fmt -check -recursive ../../..
terraform validate
terraform plan
terraform apply
terraform output alb_dns_name
```

## 5. Test the application

```bash
ALB_DNS=$(terraform output -raw alb_dns_name)
curl -i "http://${ALB_DNS}/health"
curl -i "http://${ALB_DNS}/"
```

`/health` is expected to return `200 OK`.

## 6. Pre-deploy checks

```bash
python3 -m py_compile terraform/modules/compute/app-src/app.py
terraform fmt -check -recursive terraform
(cd terraform/environments/dev  && terraform init -backend=false && terraform validate)
(cd terraform/environments/prod && terraform init -backend=false && terraform validate)
```

This project is not considered actually deployed until `plan` and `apply` have run against a real AWS account and the endpoints above have been tested.

## 7. Accessing EC2

No SSH, no key pair. Use SSM Session Manager:

```bash
aws ssm start-session --target <instance-id> --region us-east-1
sudo systemctl status ecomm-app nginx
sudo journalctl -u ecomm-app -n 100 --no-pager
sudo journalctl -u nginx -n 100 --no-pager
```

## 8. Load testing the Auto Scaling policy

`load-testing/k6-script.js` ramps traffic up to 1,000 virtual users to exercise the CPU-based scaling policy and the `alb_response_time` / `alb_5xx` alarms under load:

```bash
k6 run -e TARGET_URL=http://<alb_dns_name> load-testing/k6-script.js
```

Run this against `dev` first, and only against `prod` as a scheduled, signed-off exercise — a 1,000-VU run can itself trip the WAF rate-limit rule. This repository documents the procedure and the `p(95)<2000ms` threshold the script checks; it does not claim a specific past run's results. Record the actual numbers (whether the ASG scaled from 2 to more instances, and the p95 latency observed) wherever you keep deployment evidence for this environment.

## 9. Testing RDS failover and backups

These are the commands to exercise Multi-AZ failover and point-in-time recovery against the Terraform-managed database. Results are not included here — this section describes how to run the test, not a claim that it has been run against this specific deployment. (The root `README.md` documents an executed Multi-AZ failover test against the original, manually built environment, with evidence in `validation-tests/`.)

```bash
# Multi-AZ failover (prod only)
aws rds reboot-db-instance --db-instance-identifier <db_instance_id> --force-failover
aws rds describe-events --source-identifier <db_instance_id> --source-type db-instance

# Point-in-time recovery restore (into a NEW instance - never over the original)
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier <db_instance_id> \
  --target-db-instance-identifier <db_instance_id>-pitr-test \
  --restore-time <ISO-8601-timestamp>
```

Delete the restored `-pitr-test` instance once you've confirmed it, since it is a full second RDS instance and bills accordingly. Neither RTO nor RPO has been formally measured for this project; both commands above are how you would measure them.

## 10. Pre-deploy checks, recap

See section 6 above; run it before every `apply`.

## 11. Common issues (quick reference)

Full write-ups with cause, fix, and prevention are in [`docs/TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

| Issue | Quick check |
|---|---|
| Target not healthy | Check `/health`, Nginx, and `ecomm-app` on the instance via SSM. |
| No outbound connectivity at boot | Check the NAT Gateway and the private route table. |
| HTTPS not working | `certificate_arn` needs a valid, validated ACM certificate; without it the project is HTTP only. |
| Terraform asks for `db_instance_class` | Set it in a local tfvars file (a deliberate choice, no default) — never commit a placeholder. |
| `Error acquiring the state lock` | See `docs/TROUBLESHOOTING.md` — usually an interrupted run or a second run in parallel. |

## 12. Create / Import / Update / Destroy

The original environment was built manually. When running Terraform against an account that already has real resources under the same names, the distinction matters:

- **Create** — Terraform creates a resource that does not exist yet.
- **Import** — Terraform starts managing a resource that already exists in AWS (`terraform import <address> <real-id>`), without deleting or recreating it.
- **Update** — Terraform changes an already-managed resource to match the code.
- **Destroy** — Terraform deletes a resource it manages.

Terraform does not "discover" existing AWS resources automatically. If a resource (RDS or the ALB, for example) already exists from the original manual deploy and should be kept, run `terraform import` once before the first `apply` so Terraform doesn't try to create a duplicate. Import commands are not part of the normal deployment flow above — they apply only when this specific situation comes up.

## 13. Cleaning up

Never run `destroy` against prod casually. RDS and the state bucket both have deletion protection. For dev:

```bash
terraform plan -destroy
terraform destroy
```

Review the plan by hand before applying it — NAT Gateways, RDS, and CloudTrail keep billing even with no traffic. For production data, take and verify a final RDS snapshot before any deletion; see `docs/TROUBLESHOOTING.md` for the `prevent_destroy` behavior that guards against this by default.
