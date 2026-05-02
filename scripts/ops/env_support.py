# =============================================================================
# HOW THE django_*.py SCRIPTS WORK (read this once)
#
# On the server you would normally type:
#
#   cd …; source venv/bin/activate; set -a; source /etc/django/backend.env; set +a
#   python manage.py <command>
#
# Bash "set -a … source … set +a" loads KEY=value pairs and exports them so
# "python manage.py …" sees POSTGRES_PASSWORD, DJANGO_ALLOWED_HOSTS, etc.
#
# This module replaces that Bash block for scripts: parse_env_file() reads the
# same env file into a dict, merges it onto os.environ, and subprocess passes
# that full env to `[sys.executable, manage.py, ...]` with cwd=project root.
#
# Default env path:       /etc/django/backend.env
# Override for dev/tests: BACKEND_ENV_FILE=/path/to/.env
#
# project_root(): parent of scripts/ … i.e. the folder containing manage.py
# =============================================================================
"""
Load key=value pairs from a file into a subprocess env dict.

Default file: /etc/django/backend.env (production on EC2)
Override with environment variable BACKEND_ENV_FILE=/path/to/.env

Does not evaluate shell; supports optional ``export KEY=val`` and # comments.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


DEFAULT_ENV_PATH = "/etc/django/backend.env"


def ops_dir() -> Path:
    return Path(__file__).resolve().parent


def project_root() -> Path:
    # back-end/scripts/ops/*.py -> back-end/
    return ops_dir().parents[2]


def env_file_path() -> Path:
    return Path(os.environ.get("BACKEND_ENV_FILE", DEFAULT_ENV_PATH))


def parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    raw = path.read_text(encoding="utf-8")
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def build_subprocess_env() -> dict[str, str]:
    path = env_file_path()
    merged = dict(os.environ)
    if not path.is_file():
        print(
            f"Warning: env file not found ({path}); using current environment only.",
            file=sys.stderr,
        )
        return merged
    merged.update(parse_env_file(path))
    return merged


def django_run(extra_args: list[str]) -> int:
    root = project_root()
    manage = root / "manage.py"
    if not manage.is_file():
        print(f"Error: manage.py not found at {manage}", file=sys.stderr)
        return 127
    proc = subprocess.run(
        [sys.executable, str(manage), *extra_args],
        cwd=root,
        env=build_subprocess_env(),
    )
    return proc.returncode


def run_manage(argv: list[str]) -> None:
    sys.exit(django_run(argv))


def sudo_run(extra_args: list[str]) -> int:
    proc = subprocess.run(["sudo", *extra_args])
    return proc.returncode


def run_sudo(argv: list[str]) -> None:
    sys.exit(sudo_run(argv))
