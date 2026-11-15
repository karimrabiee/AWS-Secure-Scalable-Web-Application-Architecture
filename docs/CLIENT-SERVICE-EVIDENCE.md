# Client Service Evidence — AWS Infrastructure & CI/CD

This page maps the repository to concrete engineering work a buyer can review. It describes a portfolio implementation, not client delivery or an independent production audit.

## What this project demonstrates

- A two-Availability-Zone AWS network with public load-balancer subnets and private application/database subnets.
- Terraform modules organized by infrastructure responsibility, with separate `dev` and `prod` environment configurations.
- A GitHub Actions deployment workflow that uses AWS IAM OIDC rather than stored long-lived AWS access keys.
- A reviewed Terraform plan, an approval gate, deployment guards, and post-deployment `/health` and `/ready` checks.
- Private EC2 application instances accessed through AWS Systems Manager Session Manager rather than inbound SSH.
- An Application Load Balancer, EC2 Auto Scaling, private RDS MySQL, Secrets Manager, AWS WAF, CloudWatch alarms, CloudTrail, and VPC Flow Logs.

## Evidence available in this repository

| Evidence | Recorded result | Boundary |
|---|---|---|
| Terraform `dev` deployment | Owner-run deployment and dated evidence are documented | Not a current live availability guarantee |
| Application health | HTTP 200; 2 of 2 ALB targets healthy across two AZs | Applies to the recorded `dev` validation |
| Private compute | No public IP on the two recorded instances; IMDSv2 required | Evidence is from the documented validation session |
| Database exposure | RDS recorded as not publicly accessible and encrypted | `dev` uses single-AZ RDS by design |
| SSH exposure | No port 22 security-group rule recorded; Session Manager used | Applies to the checked VPC configuration |
| WAF | Normal request returned 200; crafted XSS query and sqlmap user-agent checks returned 403 | These are specific test requests, not a claim that all attacks are blocked |
| Automated tests | 60 tests are recorded as passing in the documented review run | 9 tests require a real database; see the test-results document |
| Terraform and pipeline checks | CI and Terraform deployment run are documented | A green CI run does not prove every AWS account prerequisite |

See [the main README](../README.md), [test results](TEST-RESULTS.md), [security controls](SECURITY-CONTROL.md), and [CI/CD design](CI-CD.md) for the underlying detail.

## Example buyer problems this work is relevant to

1. **GitHub Actions cannot deploy to AWS safely.** Review the OIDC trust relationship, repository/environment conditions, IAM permissions, and workflow permissions; then implement a scoped deployment path.
2. **Terraform infrastructure is difficult to maintain.** Review module boundaries, environment separation, backend configuration, variables, and validation checks; then refactor an agreed scope.
3. **An AWS application needs a clearer network/security baseline.** Review public exposure, security-group paths, instance access, database exposure, and selected logging controls using a read-only-first process.
4. **A deployment or Terraform run is failing.** Reproduce the error from supplied logs and configuration, identify the cause, and propose a tested, scoped fix.

These are service examples, not claims that this repository was built for a paying customer.

## Delivery approach

1. Confirm the AWS account, region, repository, environment, exact target outcome, and constraints.
2. Review supplied configuration and logs. Start read-only; do not request root credentials or long-lived IAM user access keys.
3. Agree the exact files/resources in scope, acceptance checks, exclusions, and rollback approach before changes.
4. Implement in a branch or non-production environment where practical.
5. Run the agreed checks and provide a concise handover: changed files, commands, results, assumptions, and remaining risks.

## Scope boundaries

- No compliance certification, penetration test, or formal security audit is offered.
- No guarantee of zero downtime, complete security, or fixed cost savings.
- No production changes without explicit written approval and a rollback plan.
- No destructive Terraform apply, database migration, IAM privilege expansion, or network exposure change outside the agreed scope.
- No access-key collection. Prefer customer-run commands, redacted exports, or a temporary least-privilege role when remote access is genuinely necessary.
- Kubernetes/EKS production implementation is not represented by this project.

## Suggested handover checklist

- [ ] Scope and acceptance criteria confirmed
- [ ] Relevant repository paths and AWS region confirmed
- [ ] Sensitive values redacted from shared logs and screenshots
- [ ] Plan/diff reviewed before applying changes
- [ ] Tests and validation commands recorded
- [ ] Rollback or teardown instructions supplied
- [ ] Known limitations and follow-up work documented
