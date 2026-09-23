# Troubleshooting

Real problems encountered while building, deploying, and codifying this project with Terraform.

Each issue documents the problem, cause, and practical recovery.

> Commands assume AWS CLI and Terraform are already configured.

---

## 1. Terraform Backend Bucket Did Not Exist

### Problem

`terraform init` failed because the S3 bucket configured for the Terraform backend did not exist.

### Cause

Terraform remote state requires the S3 backend bucket to exist before the environment can be initialized.

### Fix

Create the backend infrastructure first:

```
terraform -chdir=terraform/bootstrap init
terraform -chdir=terraform/bootstrap apply
```

Then configure the local `backend.hcl` with the real bucket name and initialize:

```
terraform init -backend-config=backend.hcl
```

If the backend configuration was changed:

```
terraform init -backend-config=backend.hcl -reconfigure
```

### Prevention

* Keep `backend.hcl` local and gitignored.
* Keep `backend.hcl.example` as a template.
* Never commit Terraform state.

---

## 2. `BucketAlreadyExists`

### Problem

Terraform reported:

```
Error: creating S3 Bucket (...): BucketAlreadyExists
```

### Cause

S3 bucket names are globally unique.

The bucket already existed because it had been created previously or the requested name was already in use.

### Fix

Check whether the bucket already belongs to the project.

If it exists in AWS but is not in Terraform state, import it:

```
terraform -chdir=terraform/bootstrap import aws_s3_bucket.tfstate <bucket-name>
```

Then verify:

```
terraform -chdir=terraform/bootstrap plan
```

### Prevention

Check existing AWS resources and Terraform state before creating infrastructure.

---

## 3. Terraform State Lock

### Problem

Terraform reported:

```
Error acquiring the state lock
```

or:

```
412 Precondition Failed
```

### Cause

The project uses Terraform's native S3 state locking:

```
use_lockfile = true
```

The lock prevents multiple Terraform operations from changing the same state at the same time.

### Fix

First make sure another Terraform operation is not running.

If the lock is confirmed to be stale:

```
terraform force-unlock <LOCK_ID>
```

Then retry the operation.

### Prevention

Do not disable state locking as a workaround.

---

## 4. Terraform State Was Not Committed

Terraform state can contain infrastructure information and sensitive values.

The repository therefore excludes:

```
*.tfstate
*.tfstate.*
.terraform/
```

Never commit:

```
terraform.tfstate
terraform.tfstate.backup
```

The remote S3 backend stores the environment state.

---

## 5. Existing AWS Resources Required Import

### Problem

Terraform attempted to create a resource that already existed in AWS.

Typical errors included:

```
AlreadyExists
```

or:

```
EntityAlreadyExists
```

### Cause

The AWS resource existed, but Terraform did not have it in its state.

### Fix

If the existing resource should be managed by Terraform, import it:

```
terraform import <resource-address> <resource-id>
```

Then check:

```
terraform plan
```

Review the planned changes before applying.

### Prevention

Before creating resources, check whether they already exist in AWS or Terraform state.

---

## 6. Amazon Linux 2023 AMI Configuration

### Problem

Terraform reported:

```
Reference to undeclared resource
data.aws_ami.al2023
```

### Cause

The compute configuration referenced an AMI data source that was not correctly defined.

### Fix

The compute module now obtains the Amazon Linux 2023 AMI through AWS's published SSM parameter.

This keeps AMI discovery inside the compute module.

### Prevention

Keep AMI lookup in one place instead of duplicating it across environments.

---

## 7. RDS `gp3` Storage Configuration

### Problem

RDS rejected the database storage configuration because the requested `gp3` performance settings were not valid for the selected storage size.

### Cause

The project uses a small `gp3` RDS volume.

Additional IOPS and throughput settings were unnecessary.

### Fix

The database module uses the required storage configuration without unnecessary performance parameters.

### Prevention

Keep RDS configuration simple unless there is a real performance requirement.

---

## 8. Auto Scaling Group Already Existed

### Problem

Terraform encountered an Auto Scaling Group that already existed.

### Cause

The ASG had already been created by an earlier deployment.

### Fix

If the existing ASG is the one Terraform should manage, import it:

```
terraform import module.compute.aws_autoscaling_group.app <existing-asg-name>
```

Then:

```
terraform plan
```

Review the differences before applying.

### Prevention

Import existing resources instead of creating duplicates.

---

## 9. EC2 Service Quota

### Problem

AWS rejected the requested EC2 capacity because the account did not have enough available quota.

Example:

```
You have requested more instances than your current instance limit allows
```

### Cause

AWS Service Quotas are account- and region-specific.

Terraform cannot automatically increase them.

### Fix

Check the EC2 quota in the target region.

If necessary:

* Request a quota increase.
* Temporarily reduce the ASG capacity.
* Use an instance type with available quota.

### Prevention

Check important AWS quotas before deploying a new environment.

---

## 10. RDS Deletion Protection

### Problem

`terraform destroy` could not delete the RDS database because deletion protection was enabled.

### Cause

The production database is protected against accidental deletion.

### Fix

If the database genuinely needs to be deleted, disable deletion protection deliberately:

```
deletion_protection = false
```

Apply the change:

```
terraform apply -var="deletion_protection=false"
```

Then run:

```
terraform destroy
```

### Prevention

Keep deletion protection enabled for production resources.

---

## 11. `terraform destroy` Did Not Complete

### Problem

A Terraform destroy operation stopped before all resources were deleted.

### Cause

Some AWS resources were still being used by other resources or had dependencies that needed to be removed first.

### Fix

Do not immediately delete resources manually.

First check the Terraform state:

```
terraform state list
```

Then check the plan:

```
terraform plan
```

Identify the resource causing the problem and resolve that dependency before continuing.

### Prevention

Let Terraform manage the resource lifecycle whenever possible.

Avoid manually deleting Terraform-managed resources during a normal deployment.

---

## 12. Terraform Operation Was Interrupted

### Problem

A `terraform apply` or `terraform destroy` was interrupted because of a power outage, lost connection, closed terminal, or similar issue.

### Cause

Terraform may have completed some AWS operations before the interruption.

This can temporarily leave the infrastructure in a partially changed state.

### Fix

Do not immediately run another large operation.

First check:

```
terraform state list
```

Then run:

```
terraform plan
```

Review what Terraform wants to change.

If the plan matches the expected state, continue with the required operation.

### Prevention

After an interrupted Terraform operation:

```
Check state
    ↓
Run plan
    ↓
Review changes
    ↓
Continue
```

---

## 13. Resource Replacement

### Problem

Terraform planned to replace an existing resource.

### Cause

Some Terraform configuration changes require an existing resource to be recreated.

### Fix

Always review:

```
terraform plan
```

before applying the replacement.

Pay particular attention to stateful resources such as RDS.

### Prevention

Never approve a replacement without checking what will be destroyed and recreated.

---

## 14. ALB Returned `502 Bad Gateway`

### Problem

The Application Load Balancer initially returned:

```
502 Bad Gateway
```

### Investigation

The target group and EC2 instances were checked.

The instances became healthy, and the application path was checked through Nginx and Gunicorn.

### Result

The ALB and target group configuration were confirmed to be working, so the investigation moved to the application layer.

### Prevention

When troubleshooting an ALB error, check the components in order:

```
ALB
  ↓
Target Group
  ↓
EC2
  ↓
Nginx
  ↓
Application
```

Do not change the infrastructure before identifying the failing layer.

---

## 15. Manual Changes on EC2 Are Not Terraform Changes

### Problem

A file was changed manually on an EC2 instance, but:

```
terraform plan
```

returned:

```
No changes
```

### Cause

Terraform manages infrastructure resources.

It does not track arbitrary file changes made manually inside an EC2 instance.

### Correct approach

Manual changes can be useful for temporary testing.

For the final deployment, application configuration should come from the deployment process used to create new instances.

### Prevention

Keep application initialization reproducible through the Launch Template and User Data.

The desired flow is:

```
Application Source
      ↓
Launch Template / User Data
      ↓
Auto Scaling Group
      ↓
EC2 Instances
```

---

## 16. ASG Instances Are Not Managed Individually

EC2 instances created by the Auto Scaling Group are dynamic resources.

They should not be treated as individual Terraform resources.

For example, avoid trying to replace an individual ASG instance with:

```
terraform apply -replace=<individual-ec2-instance>
```

When the Launch Template changes, use the Auto Scaling Group's instance refresh mechanism.

Example:

```
aws autoscaling start-instance-refresh \
  --auto-scaling-group-name "<ASG_NAME>"
```

Check the refresh status with:

```
aws autoscaling describe-instance-refreshes \
  --auto-scaling-group-name "<ASG_NAME>"
```

### Prevention

Manage the ASG and Launch Template rather than individual instances.

---

## 17. `terraform plan` Is Not the Same as Deployment Validation

A successful:

```
terraform plan
```

means Terraform can calculate the proposed infrastructure changes.

It does not guarantee that the deployment will work completely.

AWS can still reject the deployment because of:

* Service Quotas
* existing resources
* permissions
* application configuration
* networking issues
* service-specific requirements

Final validation should therefore include:

```
Terraform
    ↓
AWS Infrastructure
    ↓
Application
```

---

# Final Recovery Checklist

When something fails, follow this simple process:

```
1. Read the exact error
         ↓
2. Identify what failed
         ↓
3. Check Terraform state
         ↓
4. Check the AWS resource
         ↓
5. Run terraform plan
         ↓
6. Identify the root cause
         ↓
7. Make the smallest required change
         ↓
8. Validate the result
```

The main lesson from this project is:

> **Do not fix Terraform or AWS problems by guessing. Understand the error first, check Terraform state and the AWS resource, then make the smallest change required.**
