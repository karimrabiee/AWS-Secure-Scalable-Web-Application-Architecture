#!/usr/bin/env python3
"""Fail on common committed secret/artifact patterns without reading Git history."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {".git", ".terraform", ".venv", "venv", "__pycache__"}
PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"aws_secret_access_key\s*=")
]
ALLOWED_SUFFIXES = {
    ".md", ".txt", ".tf", ".tfvars.example", ".yml", ".yaml", ".py", ".sh", ".tftpl",
    ".json", ".toml",
}

violations = []
for path in ROOT.rglob("*"):
    if not path.is_file() or IGNORED_PARTS.intersection(path.parts):
        continue
    if not any(str(path).endswith(suffix) for suffix in ALLOWED_SUFFIXES):
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for pattern in PATTERNS:
        if pattern.search(text):
            violations.append(f"{path.relative_to(ROOT)} matches {pattern.pattern}")

if violations:
    print("Repository hygiene check failed:")
    print("\n".join(violations))
    sys.exit(1)
print("Repository hygiene check passed: no common committed secret patterns found.")
