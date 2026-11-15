# Fiverr Gig 01 — GitHub Actions to AWS with OIDC

Marketplace copy is written for a clear buyer outcome. It does not claim client history, production tenure, certification partnership, or guaranteed security.

## Title

I will configure GitHub Actions CI/CD deployment to AWS using OIDC

## Search tags

- github actions
- aws ci cd
- aws oidc
- github actions aws
- aws deployment

Validate these against the live Fiverr tag suggestions in the seller editor before publishing; tag availability and search demand are not guaranteed.

## Description

Need a reliable way to deploy from GitHub Actions to AWS without storing long-lived AWS access keys in repository secrets?

I will set up a clear GitHub Actions deployment workflow using AWS IAM OpenID Connect (OIDC), with permissions scoped to your repository and deployment target.

**What I can deliver**
- AWS IAM OIDC identity provider and role trust configuration
- GitHub Actions workflow for your agreed AWS deployment target
- Least-privilege permission policy scoped to the required actions
- Environment/branch restrictions where supported by your setup
- Validation steps and a concise handover guide
- Troubleshooting notes for the delivered workflow

**Supported targets (confirm one before ordering):** Amazon S3/CloudFront static site, AWS Lambda, or an agreed EC2 deployment workflow.

You will receive the workflow files, IAM configuration, setup instructions, and test evidence for the agreed scope.

**Please message me before ordering** with your repository structure, AWS region, deployment target, and current workflow/error (if any). Never send root credentials or long-lived AWS access keys.

This service does not include application development, a full infrastructure rebuild, compliance certification, or unapproved production changes.

## Packages

Prices are proposed launch prices, not verified Fiverr market medians. Adjust only after confirming estimated effort and Fiverr's current package editor/fees.

| Package | Launch price | Scope | Delivery | Revisions |
|---|---:|---|---:|---:|
| Starter | $35 | One existing GitHub repository, one AWS target, OIDC trust setup, one workflow, basic validation and handover | 3 days | 1 |
| Standard | $75 | One repository, one AWS target, reusable workflow structure, environment/branch conditions, scoped IAM policy, validation and handover | 5 days | 2 |
| Advanced | $145 | One repository, up to two agreed deployment environments for one AWS target, approval gate where applicable, reusable workflow, scoped IAM policy, troubleshooting and handover | 7 days | 2 |

**Excluded from every package:** application feature development, multi-account/multi-region rollout, Kubernetes/EKS, broad Terraform redesign, production incident response, penetration testing, compliance work, and unlisted AWS services. These require a separate written scope and quote.

## Optional extras

- Additional AWS deployment target: quote after reviewing the target and required permissions.
- Additional repository: quote after reviewing workflow differences.
- Priority delivery: only when the scope and current workload permit it.
- Post-delivery support: a separately scoped support window; no indefinite support promise.

## Buyer requirements

1. What are you deploying: S3/CloudFront, Lambda, EC2, or another AWS service?
2. Is the GitHub repository public or private, and which branch/environment should be allowed to deploy?
3. Which AWS region and account setup are involved? Share account IDs only through a safe redacted description; never share credentials.
4. Do you already have an AWS IAM OIDC provider, or should the setup include it?
5. What should count as successful deployment (URL, health endpoint, Lambda version, or another check)?

## FAQs

**Do you use AWS access keys in GitHub Secrets?**  
The intended setup uses GitHub OIDC to obtain short-lived AWS role credentials. It requires a correctly configured IAM trust relationship and scoped permissions.

**Can you work with an existing repository?**  
Yes. Share the relevant workflow files and deployment target first so I can confirm the scope before you order.

**Will you deploy directly to my production account?**  
Not by default. We agree the target environment and change plan first. Production changes require explicit written approval and a rollback approach.

**Do you guarantee zero deployment failures?**  
No. I validate the agreed workflow and report the test results, assumptions, and remaining dependencies. External AWS/GitHub configuration and application issues can affect deployment.

## Scope gate — decline or re-scope

- Requests to share root credentials, passwords, private keys, or long-lived AWS access keys.
- Unclear ownership/authorization for the GitHub repository or AWS account.
- Requests to bypass approvals, weaken security controls, or grant broad administrator permissions without a justified, approved scope.
- Unbounded production incident response or guaranteed uptime.
- Kubernetes/EKS production work, compliance certification, penetration testing, or application development.
- Multi-account or multi-region deployment unless explicitly reviewed and separately scoped.

## Pre-publish checklist

- [ ] Validate the five tags in Fiverr's current editor.
- [ ] Confirm title/category/subcategory limits in the live seller editor.
- [ ] Run the workflow against a disposable test AWS account or sandbox.
- [ ] Verify IAM trust conditions match the exact repository and branch/environment.
- [ ] Capture redacted screenshots of workflow, successful run, and IAM trust policy.
- [ ] Ensure no account IDs, ARNs, emails, tokens, IPs, or private values are visible.
- [ ] Confirm package delivery days and revisions in the live editor.
- [ ] Confirm current Fiverr fee and withdrawal method before finalizing pricing.
