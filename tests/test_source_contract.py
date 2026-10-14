"""Dependency-light source and bootstrap contract checks."""
import ast
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "terraform/modules/compute/app-src/app.py"
COMPUTE_MAIN = ROOT / "terraform/modules/compute/main.tf"
COMPUTE_VARS = ROOT / "terraform/modules/compute/variables.tf"
USER_DATA = ROOT / "terraform/modules/compute/user-data.sh.tftpl"


def test_application_source_compiles_and_defers_annotations():
    source = APP.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(APP))
    compile(tree, str(APP), "exec")
    assert "from __future__ import annotations" in source
    assert "def read_text(path: Union[str, Path]" in source


def test_template_variables_match_templatefile_arguments():
    template = USER_DATA.read_text(encoding="utf-8")
    compute_main = COMPUTE_MAIN.read_text(encoding="utf-8")
    used = set(re.findall(r"(?<!\$)\$\{([A-Za-z_]\w*)\}", template))
    passed = set(re.findall(r"^\s*([A-Za-z_]\w*)\s*=", compute_main.split("templatefile(", 1)[1].split("\n  }))", 1)[0], re.MULTILINE))
    assert used == passed, f"template placeholders {used} do not match templatefile arguments {passed}"


def test_compute_role_does_not_request_unused_database_secret():
    main = COMPUTE_MAIN.read_text(encoding="utf-8")
    variables = COMPUTE_VARS.read_text(encoding="utf-8")
    template = USER_DATA.read_text(encoding="utf-8")
    assert "secretsmanager:GetSecretValue" not in main
    assert "db_secret_arn" not in variables
    assert "get-secret-value" not in template.lower()
    assert "db.json" not in template


def test_user_data_has_bash_syntax_when_bash_is_available():
    bash = shutil.which("bash")
    if not bash:
        return
    result = subprocess.run([bash, "-n", str(USER_DATA)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_source_changes_flow_into_launch_template_and_asg_refresh():
    main = COMPUTE_MAIN.read_text(encoding="utf-8")
    variables = COMPUTE_VARS.read_text(encoding="utf-8")
    assert 'filebase64("${path.module}/app-src/app.py")' in main
    assert 'filebase64("${path.module}/app-src/requirements.txt")' in main
    assert "version = aws_launch_template.app.latest_version" in main
    assert 'variable "enable_instance_refresh"' in variables
    assert "default     = true" in variables
    assert 'health_check_type = "ELB"' in main


def test_environment_compute_calls_no_longer_pass_unused_db_credentials():
    for environment in ("dev", "prod"):
        source = (ROOT / f"terraform/environments/{environment}/main.tf").read_text(encoding="utf-8")
        compute_block = source.split('module "compute" {', 1)[1].split('\n}', 1)[0]
        assert "db_secret_arn" not in compute_block
        assert "db_address" not in compute_block
        assert "db_port" not in compute_block
