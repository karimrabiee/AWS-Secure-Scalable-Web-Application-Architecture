## Lessons Learned — Terraform Migration

Key lessons from migrating an existing AWS architecture to Terraform:

* **State matters:** Terraform state is the source of truth for managed infrastructure. Keep it remote, locked, and protected.

* **Import existing resources:** Resources created manually must be imported or reconciled before Terraform can manage them.

* **A successful plan does not guarantee apply:** AWS quotas, service limits, and provider constraints can still cause deployment failures.

* **Dependencies matter:** Resource dependencies are especially important during creation and destruction.

* **Use a remote backend:** Remote state with locking helps prevent conflicts and protects the Terraform state.

* **Handle interrupted operations carefully:** If `terraform apply` or `terraform destroy` is interrupted, Terraform may leave a stale state lock. Before running Terraform again, verify that no operation is still running, then remove the stale lock with `terraform force-unlock <LOCK_ID>`.

* **Never remove a lock blindly:** A lock should only be removed after confirming that another Terraform process is not using the state.

* **Keep secrets and state out of Git:** Never commit `.tfstate`, sensitive `.tfvars`, credentials, or backend configuration containing sensitive values.

* **Validate AWS constraints:** Terraform may accept a configuration that AWS rejects at apply time. Important AWS constraints should be reflected in variables and validation where possible.

* **Always review `terraform plan`:** Treat the plan as a safety check before every `apply`, especially when it shows resource replacement.

* **Handle partial destroys carefully:** If `terraform destroy` stops halfway, inspect `terraform state list` and run `terraform plan` before continuing. Avoid manually deleting resources or using `terraform state rm` unless you understand the state impact.

* **Protect stateful resources:** Before destroying databases or other resources containing real data, review backups, dependencies, and deletion protection.
