#!/usr/bin/env python3
"""
One command for the whole PoC: GitHub URL (or local clone) in, report out.

Usage:
    python analyse.py https://github.com/owner/repo
    python analyse.py ~/ra-tech-credit/yolov5 --name yolov5
    python analyse.py <url> --phases debt          # stop after the debt phase
    python analyse.py <url> --skip-existing        # resume an interrupted run

Steps:
    1. metrics.py      Phase 1 facts (no AI), clones the repo if given a URL
    2. run_claude.py   Phases 2-4 through Claude Code headless mode
    3. report.py       runs/<name>/report.html
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def step(title, cmd):
    print(f"\n=== {title} ===", file=sys.stderr)
    result = subprocess.run([sys.executable, *cmd], cwd=HERE)
    if result.returncode != 0:
        sys.exit(f"{title} failed (exit code {result.returncode}).")


def main():
    p = argparse.ArgumentParser(description="Run the full debt-and-credit analysis.")
    p.add_argument("target", help="GitHub URL or path to a local clone")
    p.add_argument("--name", help="run folder name (default: repository name)")
    p.add_argument("--phases", default="debt,credit,verdict")
    p.add_argument("--model", help="model passed to claude --model")
    p.add_argument("--skip-existing", action="store_true", help="skip steps whose output already exists")
    p.add_argument("--open", action="store_true", help="open the report when done")
    args = p.parse_args()

    is_url = bool(re.match(r"^(https?://|git@)", args.target))
    name = args.name or re.sub(r"\.git$", "", args.target.rstrip("/").split("/")[-1])
    run_dir = Path("runs") / name
    repo = (run_dir / "repo") if is_url else Path(args.target).expanduser().resolve()

    if args.skip_existing and (HERE / run_dir / "inventory.json").exists():
        print("\n=== Phase 1: inventory exists, skipping ===", file=sys.stderr)
    else:
        step("Phase 1: measuring the repository", ["metrics.py", args.target, "--out", str(run_dir)])

    cmd = ["run_claude.py", str(run_dir), "--repo", str(repo), "--phases", args.phases]
    if args.model:
        cmd += ["--model", args.model]
    if args.skip_existing:
        cmd.append("--skip-existing")
    step("Phases 2-4: Claude Code analysis (about 20 minutes)", cmd)

    report_cmd = ["report.py", str(run_dir)] + (["--open"] if args.open else [])
    step("Report", report_cmd)
    print(f"\nDone. Report: {HERE / run_dir / 'report.html'}", file=sys.stderr)


if __name__ == "__main__":
    main()
