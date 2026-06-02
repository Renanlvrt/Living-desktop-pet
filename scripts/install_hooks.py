#!/usr/bin/env python3
"""
scripts/install_hooks.py
─────────────────────────
Run this once from the repo root to install the pre-commit security hook.

Usage:
    python scripts/install_hooks.py
"""

import os
import shutil
import sys
import stat

REPO_ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_HOOK   = os.path.join(REPO_ROOT, "scripts", "pre-commit")
DEST_HOOK  = os.path.join(REPO_ROOT, ".git", "hooks", "pre-commit")


def install():
    if not os.path.isdir(os.path.join(REPO_ROOT, ".git")):
        print("ERROR: Not a git repository. Run from the repo root.")
        sys.exit(1)

    os.makedirs(os.path.dirname(DEST_HOOK), exist_ok=True)
    shutil.copy2(SRC_HOOK, DEST_HOOK)

    # Make executable (important on Unix; harmless on Windows)
    st = os.stat(DEST_HOOK)
    os.chmod(DEST_HOOK, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    print(f"[OK] Pre-commit hook installed at: {DEST_HOOK}")
    print("  Every commit will now be scanned for secrets.")


if __name__ == "__main__":
    install()
