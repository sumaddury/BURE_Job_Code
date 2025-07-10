import os
import subprocess
import sys
from pathlib import Path

def run_pytest(LOGGED_PATH, CLASS, TEST, repo_name, seed_value, seed_config_name, seed_config_file):
    cwd = Path.cwd()
    project_root = cwd / repo_name
    test_path = Path(LOGGED_PATH)
    if not test_path.is_absolute():
        test_path = cwd / test_path
    test_path = test_path.resolve()
    rel = test_path.relative_to(project_root)

    nodeid = f"{rel}::{CLASS}::{TEST}" if CLASS else f"{rel}::{TEST}"

    args = [
        sys.executable, "-m", "pytest",
        str(nodeid),
        "-q", "-s",
        "--seed-config-file", seed_config_file,
        "--seed-config-name", seed_config_name,
        "--seed-value",       str(seed_value),
        "--cuda"
    ]
    try:
        proc = subprocess.run(
            args,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired as e:
        return {
            "returncode": 124,
            "stdout": e.stdout.splitlines() or [],
            "stderr": (e.stderr or [f"pytest timed out after {e.timeout}s"]).splitlines(),
        }

    return {
        "returncode": proc.returncode,
        "stdout":     proc.stdout.splitlines(),
        "stderr":     proc.stderr.splitlines(),
    }