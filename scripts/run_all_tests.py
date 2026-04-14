from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRS = (
    REPO_ROOT / "packages" / "yigthinker-mcp-uipath",
    REPO_ROOT / "packages" / "yigthinker-mcp-powerautomate",
)


def run(command: list[str], cwd: Path = REPO_ROOT) -> None:
    rendered = " ".join(command)
    print(f"\n==> ({cwd}) {rendered}")
    subprocess.run(command, cwd=cwd, check=True)


def install_test_dependencies() -> None:
    run([sys.executable, "-m", "pip", "install", "-e", ".[test]"])
    run([sys.executable, "-m", "pip", "install", "-e", "packages/yigthinker-mcp-uipath[test]"])
    run([sys.executable, "-m", "pip", "install", "-e", "packages/yigthinker-mcp-powerautomate[test]"])


def run_test_suites() -> None:
    run([sys.executable, "-m", "pytest", "-q"])
    for package_dir in PACKAGE_DIRS:
        run([sys.executable, "-m", "pytest", "-q"], cwd=package_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install test dependencies and run the root + MCP package suites.",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Assume the current interpreter already has all test dependencies installed.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.skip_install:
        install_test_dependencies()
    run_test_suites()


if __name__ == "__main__":
    main()
