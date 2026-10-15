"""Repository, Terraform and workflow contract tests.

These run without AWS or Terraform. They guard the failure classes that actually broke this
project: committed merge-conflict markers, CRLF line endings inside shell templates, state or
plan files in Git, drifting template variables, and a deployment workflow that pointed at a
different state key than the one that already owned the infrastructure.
"""
import ast
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import render_user_data as renderer

try:
    import yaml
except ImportError:  # PyYAML is part of requirements-dev.txt
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
APP_SRC = ROOT / "terraform/modules/compute/app-src"
COMPUTE = ROOT / "terraform/modules/compute"
WORKFLOWS = ROOT / ".github/workflows"
SKIP_DIRS = {".git", ".terraform", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", ".ruff_cache"}
TEXT_SUFFIXES = {".md", ".txt", ".tf", ".tftpl", ".tfvars", ".hcl", ".yml", ".yaml", ".py", ".sh",
                 ".json", ".toml", ".js", ".css", ".html", ".svg", ".mmd", ".example", ".sha256"}
TEXT_NAMES = {".gitignore", ".gitattributes", "LICENSE"}


def text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or SKIP_DIRS.intersection(path.relative_to(ROOT).parts):
            continue
        if path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES:
            yield path


def rel(path):
    return path.relative_to(ROOT).as_posix()


class HygieneTests(unittest.TestCase):
    def test_no_merge_conflict_markers(self):
        marker = re.compile(r"^(<{7} |>{7} )", re.MULTILINE)
        offenders = [rel(p) for p in text_files() if marker.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [])

    def test_text_files_use_lf_line_endings(self):
        offenders = [rel(p) for p in text_files() if b"\r" in p.read_bytes()]
        self.assertEqual(offenders, [], "CRLF breaks bash user-data on Linux; keep LF")

    def test_no_state_plan_or_local_config_files(self):
        banned = ("*.tfstate", "*.tfstate.*", "*.tfplan", "tfplan", "terraform.tfvars", "backend.hcl", "*.pem")
        offenders = []
        for pattern in banned:
            offenders += [rel(p) for p in ROOT.rglob(pattern)
                          if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(ROOT).parts)]
        self.assertEqual(offenders, [])

    def test_gitattributes_enforces_lf(self):
        self.assertIn("eol=lf", (ROOT / ".gitattributes").read_text(encoding="utf-8"))

    def test_runtime_requirements_are_exactly_pinned(self):
        lines = [line.strip() for line in (APP_SRC / "requirements.txt").read_text().splitlines()]
        pins = [line for line in lines if line and not line.startswith("#")]
        self.assertTrue(pins)
        for line in pins:
            self.assertRegex(line, r"^[A-Za-z0-9_.-]+==[0-9][^\s]*$")


class ApplicationSourceTests(unittest.TestCase):
    def test_sources_parse_as_python_3_9(self):
        for path in list(APP_SRC.glob("*.py")) + [ROOT / "scripts/render_user_data.py"]:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 9))
            self.assertIn("from __future__ import annotations", path.read_text(encoding="utf-8"), path.name)

    def test_templates_comply_with_the_content_security_policy(self):
        for path in (APP_SRC / "templates").glob("*.html"):
            html = path.read_text(encoding="utf-8")
            self.assertNotRegex(html, r"\sstyle=", path.name)
            self.assertNotRegex(html, r"\son[a-z]+=", path.name)
            for script in re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.DOTALL):
                self.assertEqual(script.strip(), "", "{} contains an inline script".format(path.name))

    def test_database_password_is_never_logged_or_stored(self):
        source = (APP_SRC / "db.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"logger\.\w+\([^)]*password")
        self.assertNotRegex(source, r"(?<![\w.])open\(")


class BootstrapTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = renderer.TEMPLATE.read_text(encoding="utf-8")
        cls.rendered = renderer.render_default()
        cls.main_tf = (COMPUTE / "main.tf").read_text(encoding="utf-8")

    def test_template_variables_match_templatefile_arguments(self):
        used = set(re.findall(r"(?<!\$)\$\{(\w+)\}", self.template))
        block = self.main_tf.split("templatefile(", 1)[1].split("}))", 1)[0]
        passed = set(re.findall(r"^\s*(\w+)\s*=", block, re.MULTILINE))
        self.assertEqual(used, passed)

    def test_rendered_script_has_valid_bash_syntax(self):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("bash not available")
        with tempfile.NamedTemporaryFile("w", suffix=".sh") as handle:
            handle.write(self.rendered)
            handle.flush()
            result = subprocess.run([bash, "-n", handle.name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_user_data_is_far_below_the_ec2_limit(self):
        self.assertLess(len(self.rendered.encode("utf-8")), 12_000, "EC2 user data is limited to 16 KB")

    def test_manifest_matches_every_application_file(self):
        files = renderer.app_files()
        text = renderer.manifest(files)
        for name in files:
            self.assertIn("  " + name, text, name)
        self.assertIn("requirements.txt", files)
        self.assertEqual({p.name for p in APP_SRC.glob("*.py")}, {"app.py", "db.py"})

    def test_script_has_no_secrets_and_no_ssh(self):
        lowered = self.rendered.lower()
        for forbidden in ("password=", "aws_secret", "ssh-rsa", "authorized_keys", "get-secret-value"):
            self.assertNotIn(forbidden, lowered)

    def test_script_verifies_release_and_uses_verified_tls(self):
        self.assertIn("sha256sum --check", self.template)
        self.assertIn("truststore.pki.rds.amazonaws.com", self.template)
        self.assertIn("DB_SSL_CA=", self.template)
        self.assertIn("169.254.169.254/latest/api/token", self.template)  # IMDSv2 only
        self.assertNotIn("dnf install -y curl", self.template)

    def test_nginx_replaces_the_packaged_default_server(self):
        self.assertIn("cat > /etc/nginx/nginx.conf", self.template)
        self.assertEqual(self.template.count("listen 80 default_server"), 1)


class TerraformContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compute = (COMPUTE / "main.tf").read_text(encoding="utf-8")

    def test_instance_role_can_read_only_the_database_secret(self):
        policy = self.compute.split('data "aws_iam_policy_document" "read_db_secret"', 1)[1].split("\n}\n", 1)[0]
        self.assertIn("secretsmanager:GetSecretValue", policy)
        self.assertIn("resources = [var.db_secret_arn]", policy)
        self.assertNotIn('"*"', policy)

    def test_release_bucket_is_private_encrypted_and_tls_only(self):
        for needle in ("block_public_acls       = true", "block_public_policy     = true",
                       "ignore_public_acls      = true", "restrict_public_buckets = true",
                       "BucketOwnerEnforced", "aws:SecureTransport", "sse_algorithm = \"AES256\""):
            self.assertIn(needle, self.compute)

    def test_instances_require_imdsv2_and_have_no_keypair(self):
        self.assertIn('http_tokens   = "required"', self.compute)
        self.assertNotIn("key_name", self.compute)

    def test_asg_waits_for_release_and_permissions(self):
        asg = self.compute.split('resource "aws_autoscaling_group" "app"', 1)[1]
        for dependency in ("aws_s3_object.app", "aws_iam_role_policy.read_app_release",
                           "aws_iam_role_policy.read_db_secret"):
            self.assertIn(dependency, asg.split("launch_template {", 1)[0])

    def test_environments_wire_the_application_to_the_database(self):
        for env in ("dev", "prod"):
            source = (ROOT / "terraform/environments/{}/main.tf".format(env)).read_text(encoding="utf-8")
            block = source.split('module "compute" {', 1)[1].split("\n}\n", 1)[0]
            for expected in ("db_host", "module.database.db_address",
                             "module.database.master_user_secret_arn", "db_name"):
                self.assertIn(expected, block, env)

    def test_database_is_encrypted_private_and_password_is_managed(self):
        database = (ROOT / "terraform/modules/database/main.tf").read_text(encoding="utf-8")
        for needle in ("storage_encrypted     = true", "publicly_accessible    = false",
                       "manage_master_user_password = true"):
            self.assertIn(needle, database)

    def test_backend_state_key_convention_is_consistent(self):
        example = (ROOT / "terraform/environments/dev/backend.hcl.example").read_text(encoding="utf-8")
        self.assertIn("ecomm-platform/dev/terraform.tfstate", example)


@unittest.skipIf(yaml is None, "PyYAML not installed")
class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ci = yaml.safe_load((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))
        cls.deploy_text = (WORKFLOWS / "terraform-deploy.yml").read_text(encoding="utf-8")
        cls.deploy = yaml.safe_load(cls.deploy_text)

    @staticmethod
    def triggers(workflow):
        return workflow.get("on", workflow.get(True))

    def test_workflows_are_valid_yaml_with_expected_jobs(self):
        self.assertTrue({"python", "mysql-integration", "terraform", "hygiene"} <= set(self.ci["jobs"]))
        self.assertTrue({"plan", "apply"} <= set(self.deploy["jobs"]))

    def test_ci_runs_on_pull_requests_and_main_only(self):
        triggers = self.triggers(self.ci)
        self.assertIn("pull_request", triggers)
        self.assertEqual(triggers["push"]["branches"], ["main"])

    def test_ci_has_read_only_permissions_and_no_aws_access(self):
        self.assertEqual(self.ci["permissions"], {"contents": "read"})
        text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("configure-aws-credentials", text)
        self.assertNotIn("terraform apply", text)

    def test_deploy_is_manual_serialized_and_oidc_based(self):
        self.assertIn("workflow_dispatch", self.triggers(self.deploy))
        self.assertFalse(self.deploy["concurrency"]["cancel-in-progress"])
        self.assertEqual(self.deploy["permissions"]["id-token"], "write")
        self.assertIn("configure-aws-credentials", self.deploy_text)
        self.assertNotIn("AWS_ACCESS_KEY_ID", self.deploy_text)

    def test_deploy_uses_the_same_state_key_as_the_backend_convention(self):
        self.assertIn("ecomm-platform/{0}/terraform.tfstate", self.deploy_text)
        self.assertNotIn("TF_STATE_KEY_PREFIX", self.deploy_text)

    def test_apply_only_applies_the_reviewed_plan_and_is_smoke_tested(self):
        steps = " ".join(str(s.get("run", "")) for s in self.deploy["jobs"]["apply"]["steps"])
        self.assertIn("terraform apply -input=false tfplan", steps)
        self.assertIn("scripts/smoke-test.sh", steps)

    def test_deploy_runs_preflight_before_planning(self):
        self.assertIn("scripts/preflight.sh", self.deploy_text)
        self.assertTrue((ROOT / "scripts/preflight.sh").is_file())


if __name__ == "__main__":
    unittest.main()
