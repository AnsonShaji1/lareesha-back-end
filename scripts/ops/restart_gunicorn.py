#!/usr/bin/env python3
# =============================================================================
# MANUAL EC2 EQUIVALENT (Bash) — restart app workers after code or .env changes
#
#   sudo systemctl restart gunicorn
#
# No Django env file here — systemd reads /etc/django/backend.env via the unit,
# usually only when the service *starts*.
# =============================================================================

"""Run: sudo systemctl restart gunicorn."""

import sys
from pathlib import Path

_OPS = Path(__file__).resolve().parent
sys.path.insert(0, str(_OPS))

from env_support import run_sudo  # noqa: E402


if __name__ == "__main__":
    run_sudo(["systemctl", "restart", "gunicorn"])
