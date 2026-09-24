# Security design reference

This document describes every security control in this production-inspired architecture, the threat it mitigates, and the AWS service that implements it. The controls describe the intended Terraform configuration; they are not a substitute for a deployed-account security review.

---

## Network isolation

### VPC and subnet segmentation

The architecture uses three distinct network tiers with no direct routing between them except through explicit security group rules:

| Tier | CIDR range | Internet access | Purpose |
|---|---|---|---|
| Public | 10.0.1.0/24, 10.0.2.0/24 | Direct (via IGW) | ALB nodes, NAT Gateways |
| Application private | 10.0.11.0/24, 10.0.12.0/24 | Outbound only (via NAT) | EC2 instances |
| Database private | 10.0.21.0/24, 10.0.22.0/24 | None | RDS primary and standby |

The database subnets have **no internet route table entry at all**. Even if RDS security groups were misconfigured, the subnet routing would prevent any traffic from reaching the internet.

### Security group chaining

Security groups reference each other by group ID rather than IP ranges. This creates an explicit dependency chain where traffic at each tier can only originate from the tier immediately above it:

```
Internet
  └─ ALB-SG (accepts :80; :443 only when `certificate_arn` is configured)
       └─ EC2-SG (accepts :80 from ALB-SG only)
            └─ RDS-SG (accepts :3306 from EC2-SG only)
```

If the ALB is removed, EC2 becomes unreachable from the internet even without changing any other rule, because no other security group is permitted to send traffic to EC2-SG.

---

## Edge protection

### AWS WAF

A Regional Web ACL is attached to the Application Load Balancer. The ACL includes the **AWS Managed Rules Common Rule Set**, which covers:

- SQL injection attempts
- Cross-site scripting (XSS)
- Known malicious user agents
- HTTP protocol violations
- File inclusion attacks

The Terraform configuration enables the three AWS managed rule groups and configures the rate-based rule with an explicit **Block** action. A separate Count-mode tuning phase is not claimed by this repository; any production rollout should test and tune managed rules before enabling them for real traffic. WAF metrics are published to CloudWatch and sampled requests are visible in the WAF console.

---

## Instance access

### Systems Manager Session Manager instead of SSH

There is no SSH inbound rule anywhere in this architecture. EC2 instances are accessed through AWS Systems Manager Session Manager, which:

- Requires no open inbound port
- Uses IAM for authentication (not SSH keys)
- Logs all session activity to CloudTrail
- Works from the AWS Console or the AWS CLI (`aws ssm start-session`)

The EC2 IAM role has the AWS-managed `AmazonSSMManagedInstanceCore` policy for Session Manager and one additional inline policy. The inline policy grants only `secretsmanager:GetSecretValue` on the exact RDS master-secret ARN supplied to the compute module. It does not grant wildcard access to Secrets Manager.

### IMDSv2 enforcement

The launch template configures instances to require IMDSv2 (token-based) for all Instance Metadata Service calls. This prevents SSRF attacks from using the metadata service to retrieve IAM credentials.

All metadata access in the `user-data.sh` script uses the two-step IMDSv2 pattern:
```bash
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
AZ=$(curl -s -H "X-aws-ec2-metadata-token: ${TOKEN}" \
  "http://169.254.169.254/latest/meta-data/placement/availability-zone")
```

---

## Data protection

### RDS encryption at rest

The RDS instance is created with storage encryption enabled using an AWS-managed KMS key. This encrypts:
- The database storage volume
- Automated backups
- Read replicas (if created)
- Snapshots

Encryption cannot be enabled after an RDS instance is created, which is why it is set at creation time.

### S3 bucket for CloudTrail

The audit log S3 bucket has:
- All public access blocked
- Default encryption (SSE-KMS using the AWS-managed S3 KMS key unless a customer-managed key is configured)
- A bucket policy that only allows CloudTrail to write to it
- Log file validation enabled on the trail (CloudTrail creates a digest file that lets you detect if log files are modified or deleted)

---

## Audit and monitoring

### CloudTrail

A multi-region trail records every API call made in the account, including:
- EC2 instance launches and terminations
- Security group changes
- RDS configuration changes
- IAM policy modifications
- S3 bucket policy changes
- WAF rule changes

Logs are delivered to the audit S3 bucket within approximately 15 minutes of the API call. Log file validation is enabled so any tampering with delivered log files is detectable.

### VPC Flow Logs

Flow Logs capture all network traffic at the VPC level, including:
- Accepted and rejected connections
- Source and destination IPs and ports
- Bytes transferred

Logs are delivered to a CloudWatch Logs group and can be queried using CloudWatch Logs Insights. Example query to find all rejected traffic:
```
fields @timestamp, srcAddr, dstAddr, dstPort, action
| filter action = "REJECT"
| sort @timestamp desc
| limit 50
```

### CloudWatch Alarms

The CPU alarm at 70% for 5 minutes serves both an operational and a light security function. A sudden spike in CPU on the application tier could indicate a cryptomining attack, a DDoS reaching the application layer, or a runaway process introduced through a vulnerability.

---

## IAM least privilege

| Principal | Permissions | Reason |
|---|---|---|
| EC2 instance role | `AmazonSSMManagedInstanceCore` plus `secretsmanager:GetSecretValue` on one exact ARN | Session Manager plus runtime retrieval of the RDS master secret |
| CloudTrail | `s3:PutObject` to the audit bucket only | CloudTrail only needs to write logs |
| VPC Flow Logs | `logs:CreateLogGroup`, `logs:CreateLogDelivery`, `logs:PutLogEvents` | Minimum to deliver flow logs |

No access keys are created. No IAM users are given console access to this specific account beyond the operator IAM user used to build the architecture.

---

## Threat model summary

| Threat | Mitigation |
|---|---|
| Web application attacks (SQLi, XSS) | AWS WAF with managed rules |
| Unencrypted traffic interception | HTTPS enforcement via ACM + HTTP redirect when `certificate_arn` is configured; HTTP-only mode remains available for bootstrap/dev |
| Direct EC2 compromise from internet | Private subnets, no public IP, no inbound rule from internet |
| Database exposure | DB-tier subnets have no internet route; RDS-SG accepts from EC2-SG only |
| Unauthorized API access | CloudTrail logs all API calls; IAM least privilege |
| Instance metadata SSRF | IMDSv2 required on all instances |
| Unauthorized shell access | No SSH; SSM Session Manager with IAM auth |
| Data exfiltration via S3 | Audit bucket is private; only CloudTrail can write to it |
| Undetected scaling attack | CloudWatch alarm + SNS notification on sustained CPU spike |
| Network traffic anomalies | VPC Flow Logs to CloudWatch Logs for query and alerting |
