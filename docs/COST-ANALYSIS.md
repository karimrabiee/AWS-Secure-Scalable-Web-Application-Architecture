# Cost analysis

This document breaks down the estimated hourly and monthly cost of running this architecture in `us-east-1` at the minimum configuration used for this project, along with the cost decisions made during the design phase.

All prices are approximate and based on on-demand rates as of mid-2025. Prices vary by region and change over time — verify current rates at [aws.amazon.com/pricing](https://aws.amazon.com/pricing).

---

## Hourly cost breakdown (minimum configuration)

| Service | Configuration | Hourly cost |
|---|---|---|
| EC2 (×2) | t3.micro, on-demand | ~$0.021 |
| NAT Gateway (×2) | per-hour charge, not including data | ~$0.090 |
| RDS MySQL Multi-AZ | db.t3.micro | ~$0.034 |
| Application Load Balancer | per-hour charge, not including LCUs | ~$0.008 |
| CloudTrail | first trail per region is free | $0.000 |
| CloudWatch | 10 metrics, 1 dashboard, 1 alarm free tier | ~$0.000 |
| SNS | first 1 million notifications free | $0.000 |
| S3 (audit logs) | minimal storage, within free tier | ~$0.000 |
| VPC Flow Logs | ingestion to CloudWatch Logs, ~1GB/day | ~$0.002 |
| **Total** | | **~$0.155/hr** |

**Per day:** ~$3.72  
**Per week:** ~$26  
**Per month (if left running):** ~$113

> The NAT Gateways account for roughly 58% of the total cost. Each NAT Gateway has a flat $0.045/hr charge plus $0.045/GB of data processed. For a learning or demo environment, this is the first service to destroy when not actively using the architecture.

---

## Cost decisions made during design

### Two NAT Gateways instead of one

**Decision:** Deploy NAT-A in `us-east-1a` and NAT-B in `us-east-1b`, each serving only the EC2 instances in their own AZ.

**Cost impact:** Doubles the NAT Gateway hourly charge ($0.09/hr vs $0.045/hr).

**Reason:** A single NAT Gateway creates a single point of failure for outbound internet access. If the AZ containing the single NAT fails, all EC2 instances lose outbound connectivity — breaking software updates, AWS API calls, and any external integrations — even though their AZ is healthy. Two NAT Gateways ensure each AZ is fully independent. For a production workload where 99.9% uptime matters, this cost is justified.

**When to use one NAT Gateway instead:** For pure development or staging environments where occasional outbound failures during AZ events are acceptable and cost savings are the priority.

### t3.micro for EC2 and db.t3.micro for RDS

**Decision:** Use burstable instance types rather than general-purpose or memory-optimized.

**Cost impact:** t3.micro is the smallest instance type eligible for the AWS Free Tier (750 hours/month free for the first 12 months per account). db.t3.micro is the smallest Multi-AZ-eligible RDS instance.

**Reason:** For a portfolio project and exam preparation context, a t3.micro provides enough CPU and memory to demonstrate all architecture features, including Auto Scaling and load balancing. A production system serving real traffic would need at least t3.small for EC2 and db.t3.small or larger for RDS, depending on query volume.

### Systems Manager Session Manager instead of Bastion Host

**Decision:** Use SSM Session Manager for EC2 access, eliminating the need for a Bastion Host EC2 instance.

**Cost impact:** Saves approximately $0.0104/hr (t3.micro on-demand in us-east-1) plus one Elastic IP address.

**Reason:** A traditional Bastion Host pattern requires a running EC2 instance in a public subnet, an Elastic IP, an SSH key pair, and an open inbound port 22 on a security group. SSM Session Manager provides equivalent functionality with better security (IAM-based auth, no SSH keys, full session logging to CloudTrail) at zero additional cost beyond the IAM role already attached to the EC2 instances.

### Auto Scaling minimum of 2 instances

**Decision:** Set `min_size = 2` rather than `min_size = 1`.

**Cost impact:** Doubles the EC2 cost during periods of zero or minimal load.

**Reason:** A minimum of 1 instance with Multi-AZ enabled means the single instance is in one AZ. If that AZ has an issue, the ASG needs time to launch a new instance in the other AZ, detect it as healthy via the ELB health check (60-second grace period plus health check interval), and register it with the ALB before traffic resumes. A minimum of 2 means one instance is always running in each AZ, and the ALB can immediately route to the surviving AZ without waiting for a launch.

### RDS 7-day backup retention

**Decision:** Set backup retention to 7 days (the minimum that supports point-in-time recovery).

**Cost impact:** Automated backups for RDS storage up to the provisioned storage size are free. For 20 GB RDS storage, 7 days of backups consume up to 140 GB of backup storage, which is free within the RDS backup storage free tier (equal to the sum of provisioned database storage in the region).

**Reason:** 7 days provides a recovery window for most operational incidents while staying within the free backup tier. A production system would typically use 14–35 days, incurring backup storage charges above the free tier.

---

## Monthly savings checklist

If you're running this for learning purposes and want to minimize cost:

1. **Destroy resources when not actively testing.** `terraform destroy` or manually delete in this order: ASG → ALB + TG → RDS → NAT Gateways + EIPs → VPC.
2. **Use a single NAT Gateway** if AZ-level outbound resilience is not required for your current test.
3. **Stop RDS instead of deleting** if you want to preserve data between sessions. Stopped RDS instances do not incur instance-hour charges but continue to charge for storage and Multi-AZ standby.
4. **Set an AWS Budgets alert at $5** so a forgotten resource cannot accumulate a large unexpected charge.
5. **Check the Free Tier dashboard** in the Billing console regularly. The first 12 months of a new account include 750 hours/month of t3.micro EC2 and 750 hours/month of db.t3.micro RDS (single-AZ only — Multi-AZ is not covered by the Free Tier).

---

## Cost vs. architecture trade-off summary

| Trade-off | Cheaper option | More resilient option | This project uses |
|---|---|---|---|
| NAT Gateways | 1 shared (saves $0.045/hr) | 2 per-AZ | 2 per-AZ |
| EC2 minimum | 1 instance | 2 instances (one per AZ) | 2 instances |
| RDS | Single-AZ | Multi-AZ (doubles cost) | Multi-AZ |
| Instance access | Bastion Host (adds $0.01/hr) | SSM Session Manager ($0) | SSM |
| Backup retention | 1 day (less recovery window) | 7 days (free tier) | 7 days |
