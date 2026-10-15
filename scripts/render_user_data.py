#!/usr/bin/env python3
"""Render terraform/modules/compute/user-data.sh.tftpl the way Terraform's templatefile() does.

Supports the subset the template uses: ``${name}`` substitution and the doubled-dollar escape.
Used by the tests and handy for debugging:

    python scripts/render_user_data.py > /tmp/user-data.sh && bash -n /tmp/user-data.sh
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[1]
COMPUTE = ROOT / "terraform" / "modules" / "compute"
APP_SRC = COMPUTE / "app-src"
TEMPLATE = COMPUTE / "user-data.sh.tftpl"

PLACEHOLDER = re.compile(r"(?<!\$)\$\{(\w+)\}")

SAMPLE_VARS = {
    "app_bucket": "ecomm-platform-dev-app-123456789012",
    "db_host": "dev-db.abc123.us-east-1.rds.amazonaws.com",
    "db_port": "3306",
    "db_name": "appdb",
    "db_secret_arn": "arn:aws:secretsmanager:us-east-1:123456789012:secret:rds!db-example-AbCdEf",
    "aws_region": "us-east-1",
}


def app_files() -> Dict[str, str]:
    """Same selection as the Terraform locals: everything under app-src/ except bytecode."""
    files = {}
    for path in sorted(APP_SRC.rglob("*")):
        rel = path.relative_to(APP_SRC).as_posix()
        if path.is_file() and not rel.endswith(".pyc") and not rel.startswith("__pycache__"):
            files[rel] = path.read_text(encoding="utf-8")
    return files


def manifest(files: Dict[str, str]) -> str:
    """Same format as the Terraform local: '<sha256>  <relative path>' per file, sorted."""
    return "\n".join(
        "{}  {}".format(hashlib.sha256(content.encode("utf-8")).hexdigest(), name)
        for name, content in sorted(files.items())
    )


def render(template: str, variables: Dict[str, str]) -> str:
    rendered = PLACEHOLDER.sub(lambda m: variables[m.group(1)], template)
    return rendered.replace("$${", "${")


def render_default() -> str:
    files = app_files()
    text = manifest(files)
    variables = dict(SAMPLE_VARS)
    variables["app_manifest"] = text
    variables["app_release"] = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return render(TEMPLATE.read_text(encoding="utf-8"), variables)


if __name__ == "__main__":
    sys.stdout.write(render_default())
