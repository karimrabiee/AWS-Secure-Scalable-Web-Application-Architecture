# Release notes

## Release scope

This release is a professional documentation and release-readiness pass over the existing Nimbus Store three-tier project. It does not add a new AWS service, change the architecture, apply infrastructure, or modify a live account.

## Changes

- Reworked the root README so it distinguishes current source readiness from dated, owner-supplied AWS evidence.
- Removed stale workflow-run claims and detailed runtime references from the root README; the evidence remains in `docs/TEST-RESULTS.md`.
- Changed the root RDS badge from a prod-specific Multi-AZ claim to a neutral MySQL label because `dev` is intentionally single-AZ and `prod` is Multi-AZ.
- Added a concise release contract that explains what green CI proves and what still requires AWS verification.
- Added `docs/RELEASE-CHECKLIST.md` for pull requests, dev deployment, prod deployment and post-apply verification.
- Marked `docs/DEPLOYMENT-GUIDE.md` as a historical Console-build reference. Terraform and the guarded GitHub Actions workflow are the maintained path.
- Added the release checklist to the documentation index.

## Verification

The following checks passed in a clean checkout of this release:

- Ruff: clean.
- Pytest: 51 passed; 9 database integration tests skipped locally because no `TEST_DB_HOST` was supplied. The CI workflow starts MySQL 8.4 for those tests.
- Runtime dependency audit: no known vulnerabilities.
- Repository hygiene: no common committed secret, state, plan or conflict-marker findings.
- GitHub Actions lint: clean with actionlint 1.7.12.
- Terraform format: clean with Terraform 1.10.5.
- Terraform validation: bootstrap, dev and prod all valid with backend disabled.
- Git diff whitespace check: clean.

A clean local or CI result does not prove that a particular AWS account has enough quota, that the remote state object is the intended one, or that an OIDC role has the required permissions. Use the deployment workflow and `docs/RELEASE-CHECKLIST.md` for those checks.
