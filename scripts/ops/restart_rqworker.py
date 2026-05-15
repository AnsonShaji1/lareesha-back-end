#!/usr/bin/env python3
# =============================================================================
# MANUAL EC2 EQUIVALENT (Bash)
#
#   sudo systemctl restart rqworker
# =============================================================================

"""Run: sudo systemctl restart rqworker."""

import sys
from pathlib import Path

_OPS = Path(__file__).resolve().parent
sys.path.insert(0, str(_OPS))

from env_support import run_sudo  # noqa: E402


if __name__ == "__main__":
    run_sudo(["systemctl", "restart", "rqworker"])
