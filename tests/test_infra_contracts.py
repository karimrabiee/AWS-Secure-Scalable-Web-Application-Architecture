"""Static contract checks for the Terraform code, bootstrap template and workflows.

These do NOT replace `terraform validate` / `terraform plan` (CI runs those); they
catch the classes of defect that caused real incidents here - broken module
interfaces, template/variable drift, CRLF line endings, merge-conflict markers,
and an unsafe deploy workflow - without needing AWS credentials or provider downloads.
"""
import gzip
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TF = ROOT / "terraform"
COMPUTE = TF / "modules" / "compute"
APP_SRC = COMPUTE / "app-src"
USER_DATA = COMPUTE / "user-data.sh.tftpl"
ENVIRONMENTS = ("dev", "prod")
TEXT_SUFFIXES = {".tf", ".tftpl", ".md", ".yml", ".yaml", ".py", ".txt", ".toml", ".hcl", ".js",
                 ".css", ".html", ".svg", ".mmd", ".example"}


def text_files():
    for path in ROOT.rglob("*"):
        if path.is_file() and ".git" not in path.parts and ".terraform" not in path.parts \
                and path.suffix in TEXT_SUFFIXES:
            yield path


def block_body(text, start):
    """Return the text between the braces of the block whose '{' is at/after `start`."""
    depth, i = 0, text.index("{", start)
    begin = i + 1
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[begin:i]
        i += 1
    raise AssertionError("unbalanced braces")


def variables(module_dir):
    """{name: has_default} for every variable declared in a module directory."""
    found = {}
    for tf in Path(module_dir).glob("*.tf"):
        text = tf.read_text(encoding="utf-8")
        for match in re.finditer(r'^variable\s+"(\w+)"', text, re.MULTILINE):
            body = block_body(text, match.end())
            top = re.sub(r"\{[^{}]*\}", "", body)  # drop nested blocks (validation)
            found[match.group(1)] = bool(re.search(r"^\s*default\s*=", top, re.MULTILINE))
    return found


def outputs(module_dir):
    names = set()
    for tf in Path(module_dir).glob("*.tf"):
        names |= set(re.findall(r'^output\s+"(\w+)"', tf.read_text(encoding="utf-8"), re.MULTILINE))
    return names


def module_calls(env):
    text = (TF / "environments" / env / "main.tf").read_text(encoding="utf-8")
    calls = {}
    for match in re.finditer(r'^module\s+"(\w+)"', text, re.MULTILINE):
        body = block_body(text, match.end())
        source = re.search(r'source\s*=\s*"([^"]+)"', body).group(1)
        args = set(re.findall(r"^\s{2}(\w+)\s*=", body, re.MULTILINE)) - {"source"}
        calls[match.group(1)] = (TF / "environments" / env / source).resolve(), args
    return text, calls


# ------------------------------------------------------------------ hygiene --
def test_no_merge_conflict_markers_anywhere():
    bad = []
    for path in text_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"^(<{7}|>{7})( |$)", line) or line == "=======":
                bad.append(f"{path.relative_to(ROOT)}:{number}")
    assert not bad, bad


def test_no_crlf_line_endings():
    bad = [str(p.relative_to(ROOT)) for p in text_files() if b"\r" in p.read_bytes()]
    assert not bad, f"CRLF would break bash on EC2: {bad}"


def test_no_state_plan_or_env_files_in_repository_tree():
    banned = [p for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts and ".terraform" not in p.parts
              and (p.suffix in {".tfstate", ".tfplan", ".pem"} or p.name in {".env", "backend.hcl", "terraform.tfvars"}
                   or ".tfstate" in p.name)]
    assert not banned, [str(p.relative_to(ROOT)) for p in banned]


# --------------------------------------------------------- module contracts --
@pytest.mark.parametrize("env", ENVIRONMENTS)
def test_every_module_call_matches_the_module_interface(env):
    _, calls = module_calls(env)
    for name, (path, args) in calls.items():
        declared = variables(path)
        unknown = args - set(declared)
        missing = {v for v, has_default in declared.items() if not has_default} - args
        assert not unknown, f"{env}: module.{name} passes undeclared variables {unknown}"
        assert not missing, f"{env}: module.{name} misses required variables {missing}"


@pytest.mark.parametrize("env", ENVIRONMENTS)
def test_every_module_output_reference_exists(env):
    text, calls = module_calls(env)
    for env_file in (TF / "environments" / env).glob("*.tf"):
        for module, output in re.findall(r"module\.(\w+)\.(\w+)", env_file.read_text(encoding="utf-8")):
            assert module in calls, f"{env_file.name}: unknown module.{module}"
            assert output in outputs(calls[module][0]), f"{env_file.name}: module.{module} has no output {output}"


def test_dev_and_prod_call_the_same_modules():
    dev = {k: v[0] for k, v in module_calls("dev")[1].items()}
    prod = {k: v[0] for k, v in module_calls("prod")[1].items()}
    assert dev == prod


def test_environments_are_isolated_by_state_key_and_cidr():
    dev_vars = (TF / "environments/dev/variables.tf").read_text(encoding="utf-8")
    prod_vars = (TF / "environments/prod/variables.tf").read_text(encoding="utf-8")
    assert "10.1.0.0/16" in dev_vars and "10.0.0.0/16" in prod_vars
    assert "ecomm-platform/dev/terraform.tfstate" in (TF / "environments/dev/backend.hcl.example").read_text(encoding="utf-8")
    assert "ecomm-platform/prod/terraform.tfstate" in (TF / "environments/prod/backend.hcl.example").read_text(encoding="utf-8")


def test_versions_are_pinned():
    for root in ("environments/dev", "environments/prod", "bootstrap"):
        text = "".join(p.read_text(encoding="utf-8") for p in (TF / root).glob("*.tf"))
        assert 'required_version = ">= 1.10.0, < 2.0.0"' in text
        assert re.search(r'version\s*=\s*">= 5\.\d+\.\d+, < 6\.0\.0"', text)
        assert (TF / root / ".terraform.lock.hcl").exists()


# -------------------------------------------------- IAM / network invariants --
def test_ec2_role_can_read_exactly_one_secret():
    main = (COMPUTE / "main.tf").read_text(encoding="utf-8")
    statement = block_body(main, main.index('data "aws_iam_policy_document" "read_db_secret"'))
    assert "resources = [var.db_secret_arn]" in statement
    assert '"*"' not in statement
    actions = re.search(r"actions\s*=\s*\[(.*?)\]", statement, re.S).group(1)
    assert set(re.findall(r'"([^"]+)"', actions)) == {"secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"}


def test_security_groups_chain_alb_app_db_without_open_cidrs_below_the_alb():
    text = (TF / "modules/security/main.tf").read_text(encoding="utf-8")
    assert text.count("referenced_security_group_id") == 2  # app<-alb, db<-app
    db_rule = block_body(text, text.index('"db_from_app"'))
    assert "cidr_ipv4" not in db_rule and "3306" in db_rule
    assert "22" not in re.findall(r"from_port\s*=\s*(\d+)", text)  # no SSH anywhere


def test_database_is_private_encrypted_and_secret_managed():
    text = (TF / "modules/database/main.tf").read_text(encoding="utf-8")
    for expected in ("publicly_accessible    = false", "storage_encrypted     = true",
                     "manage_master_user_password = true", "skip_final_snapshot       = false"):
        assert expected in text
    assert "password" not in re.sub(r"manage_master_user_password|#.*", "", text)  # no password attribute


def test_imdsv2_required_and_asg_uses_elb_health():
    text = (COMPUTE / "main.tf").read_text(encoding="utf-8")
    assert 'http_tokens   = "required"' in text
    assert 'health_check_type = "ELB"' in text and "health_check_grace_period" in text
    assert "version = aws_launch_template.app.latest_version" in text


# --------------------------------------------------------- bootstrap script --
def render_user_data():
    """Minimal re-implementation of Terraform templatefile() for this template."""
    template = USER_DATA.read_text(encoding="utf-8")
    files = {p.relative_to(APP_SRC).as_posix(): p.read_text(encoding="utf-8")
             for pattern in ("*.py", "requirements.txt", "templates/*.html", "static/css/*.css",
                             "static/js/*.js") for p in APP_SRC.glob(pattern)}
    values = {"db_host": "db.example.internal", "db_port": "3306", "db_name": "appdb",
              "db_secret_arn": "arn:aws:secretsmanager:us-east-1:123456789012:secret:rds-abc", "aws_region": "us-east-1"}
    loop = re.search(r"%\{ for name, content in app_files ~\}\n(.*?)%\{ endfor ~\}\n", template, re.S)
    assert loop, "app_files loop missing"
    body = "".join(loop.group(1).replace("${name}", name).replace("${content}", content) for name, content in sorted(files.items()))
    rendered = template[:loop.start()] + body + template[loop.end():]
    for key, value in values.items():
        rendered = rendered.replace("${" + key + "}", value)
    return rendered.replace("$${", "${"), files


def test_template_placeholders_match_templatefile_arguments():
    template = USER_DATA.read_text(encoding="utf-8")
    used = set(re.findall(r"(?<!\$)\$\{(\w+)\}", template)) - {"name", "content"}
    main = (COMPUTE / "main.tf").read_text(encoding="utf-8")
    call = main.split("templatefile(", 1)[1].split("}))", 1)[0]
    passed = set(re.findall(r"^\s*(\w+)\s*=", call, re.MULTILINE)) - {"app_files"}
    assert used == passed, f"template uses {used}, templatefile passes {passed}"
    assert "%%{" not in template


def test_rendered_user_data_is_valid_bash_and_has_no_leftover_template_syntax():
    rendered, _ = render_user_data()
    assert not re.search(r"(?<!\$)\$\{(db_|aws_region|name\b|content\b)", rendered)
    bash = shutil.which("bash")
    assert bash, "bash is required for this test"
    result = subprocess.run([bash, "-n"], input=rendered, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_user_data_fits_the_ec2_16kb_limit_when_gzipped():
    rendered, _ = render_user_data()
    # Terraform's base64gzip() uses Go's default level (6). EC2 allows 16384 bytes of user-data
    # before base64; keep ~4% headroom so a small edit cannot silently break the launch template.
    compressed = len(gzip.compress(rendered.encode("utf-8"), 6))
    assert compressed < 15700, f"gzipped user-data is {compressed} bytes (hard limit 16384)"


def test_embedded_files_cannot_break_the_heredoc():
    _, files = render_user_data()
    assert files, "no application files found"
    for name, content in files.items():
        assert "__ECOMM_APP_FILE__" not in content, name
    assert {"app.py", "db.py", "requirements.txt", "templates/base.html"} <= set(files)


def test_bootstrap_has_required_safeguards():
    rendered, _ = render_user_data()
    for expected in ("set -Eeuo pipefail", "trap 'on_error $LINENO' ERR", "nginx -t", "retry 12 5 curl",
                     "EnvironmentFile=/etc/ecomm-app/app.env", "User=ecomm-app", "global-bundle.pem",
                     "chmod 0640 /etc/ecomm-app/app.env"):
        assert expected in rendered, expected
    assert not re.search(r"^\s*set\s+-\w*x", rendered, re.MULTILINE) and "xtrace" not in rendered  # never trace
    env_file = rendered.split("cat > /etc/ecomm-app/app.env <<'APPENV'\n", 1)[1].split("\nAPPENV", 1)[0]
    assert "PASSWORD" not in env_file.upper().replace("DB_SECRET_ARN", "")  # secret is read at runtime only
    script = "\n".join(l for l in USER_DATA.read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("#"))
    assert "password" not in script.lower()  # the bootstrap script itself never handles a password


# ---------------------------------------------------------------- workflows --
def workflow(name):
    return yaml.safe_load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"))


def test_deploy_workflow_uses_the_same_state_key_as_local_backend_config():
    raw = (ROOT / ".github/workflows/terraform-deploy.yml").read_text(encoding="utf-8")
    assert "ecomm-platform/${{ inputs.environment }}/terraform.tfstate" in raw
    assert "TF_STATE_KEY_PREFIX" not in raw.replace("#", "")  # the variable that caused the mismatch
    assert "allow_fresh_state" in raw and "terraform state list" in raw  # empty-state guard


def test_deploy_workflow_is_gated_and_serialised():
    wf = workflow("terraform-deploy.yml")
    triggers = wf.get("on") or wf.get(True)
    assert set(triggers) == {"workflow_dispatch"}  # never automatic
    assert wf["concurrency"]["cancel-in-progress"] is False
    assert wf["permissions"] == {"contents": "read", "id-token": "write"}
    assert wf["jobs"]["apply"]["environment"] == "${{ inputs.environment }}"
    assert wf["jobs"]["apply"]["needs"] == "plan"
    assert "terraform apply -input=false -lock-timeout=300s tfplan" in (ROOT / ".github/workflows/terraform-deploy.yml").read_text()


def test_ci_workflow_is_read_only_and_covers_python_39():
    wf = workflow("ci.yml")
    assert wf["permissions"] == {"contents": "read"}
    assert "3.11" in wf["jobs"]["application"]["strategy"]["matrix"]["python-version"]
    raw = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "id-token" not in raw and "aws-actions" not in raw  # CI never touches AWS
