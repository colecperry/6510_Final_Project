#!/usr/bin/env python3
"""
Phases 2-4 of the technical debt / technical credit PoC, run through Claude Code
in headless mode (claude -p).

Each phase runs as a separate claude process, so it starts with a fresh session
and only sees the saved files from earlier phases. Claude is limited to read-only
tools, and returns JSON on stdout; this script validates it and saves it.

Usage (after metrics.py has produced runs/<name>/inventory.json):
    python run_claude.py runs/yolov5 --repo ~/ra-tech-credit/yolov5
    python run_claude.py runs/yolov5                      # uses runs/yolov5/repo if it exists
    python run_claude.py runs/yolov5 --phases debt        # run one phase
    python run_claude.py runs/yolov5 --model opus         # pass a model to claude

Output, per phase, in the run folder:
    02-debt.json, 03-credit.json, 04-verdict.json   validated phase results
    raw/<phase>.response.json                       full headless response (cost, usage, session id)
    raw/<phase>.prompt.md                           the exact prompt sent
    run_log.json                                    versions, timings and validation results
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROMPTS = HERE / "prompts"

PHASES = {
    "debt": {"file": "02-debt.md", "out": "02-debt.json"},
    "credit": {"file": "03-credit.md", "out": "03-credit.json"},
    "verdict": {"file": "04-verdict.md", "out": "04-verdict.json"},
}

# Read-only tools. No Write or Edit, and only git subcommands that cannot change the working tree
# (a blanket Bash(git:*) would also allow git checkout or git reset).
READ_ONLY_GIT = ["log", "show", "grep", "ls-files", "rev-list", "rev-parse", "blame", "diff", "shortlog", "cat-file"]
DEFAULT_TOOLS = ",".join(["Read", "Grep", "Glob", "Bash(wc:*)", "Bash(ls:*)"]
                         + [f"Bash(git {c}:*)" for c in READ_ONLY_GIT])
TIMEOUT_SECONDS = 45 * 60

DOMAIN = {
    "python": {
        "debt": '- "ml": machine-learning debt from Sculley et al. (2015): glue code, pipeline jungles, '
                'dead experimental code paths, configuration debt and hidden data dependencies',
        "credit": '- "ml": machine-learning credit: reproducibility of results, experiment-tracking integrations, '
                  'configuration that makes experiments cheap, and tools such as automatic batch sizing or hyperparameter search',
    },
    "java": {
        "debt": '- "systems": distributed-systems debt: error-handling shortcuts, concurrency workarounds, '
                'hardcoded configuration, and missing retry or timeout handling',
        "credit": '- "systems": distributed-systems credit: resilience patterns (retries, circuit breakers, timeouts), '
                  'observability (logging, metrics, tracing), versioned APIs and externalised configuration',
    },
}

LEVELS = {"low", "medium", "high"}
VERDICTS = {"clearly_in_debt", "leaning_debt", "balanced", "leaning_credit", "clearly_in_credit"}
STATUS = {"debt": {"realised", "potential"}, "credit": {"realised", "potential", "over_engineering"}}
ITEM_KEYS = ["id", "kind", "decision_id", "category", "title", "description", "evidence", "basis",
             "confidence_exists", "confidence_impact", "status", "frequency", "footprint", "impact"]


# ---------------------------------------------------------------- prompts

def build_prompt(phase: str, run_dir: Path, inventory: dict) -> str:
    meta = inventory["meta"]
    lang = inventory["language"]["primary"]
    domain = DOMAIN.get(lang, {"debt": "", "credit": ""})
    values = {
        "{head_short}": meta["head_short"],
        "{window_since}": meta["window"]["since"],
        "{window_until}": meta["window"]["until"],
        "{repo_name}": meta["source"],
        "{language}": lang,
        "{inventory_path}": str((run_dir / "inventory.json").resolve()),
        "{debt_path}": str((run_dir / PHASES["debt"]["out"]).resolve()),
        "{credit_path}": str((run_dir / PHASES["credit"]["out"]).resolve()),
        "{domain_debt}": domain["debt"],
        "{domain_credit}": domain["credit"],
    }
    text = (PROMPTS / "common.md").read_text() + "\n\n" + (PROMPTS / PHASES[phase]["file"]).read_text()
    # Plain replacement rather than str.format, because the templates contain JSON braces.
    for k, v in values.items():
        text = text.replace(k, v)
    return text


# ---------------------------------------------------------------- claude

def claude_version() -> str:
    try:
        return subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()
    except FileNotFoundError:
        sys.exit("The 'claude' command was not found. Install Claude Code and check 'claude --version'.")


def call_claude(prompt: str, repo: Path, run_dir: Path, tools: str, model: str | None,
                extra: list[str]) -> dict:
    cmd = ["claude", "-p", "--output-format", "json",
           "--allowedTools", tools,
           "--add-dir", str(run_dir.resolve())]
    if model:
        cmd += ["--model", model]
    cmd += extra
    started = time.time()
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                          cwd=repo, timeout=TIMEOUT_SECONDS)
    elapsed = round(time.time() - started, 1)
    if proc.returncode != 0:
        # With --output-format json, Claude Code reports errors on stdout, not stderr, so keep both.
        (run_dir / "raw").mkdir(exist_ok=True)
        (run_dir / "raw" / "last_error.txt").write_text(
            f"exit code: {proc.returncode}\n\n--- stdout ---\n{proc.stdout}\n\n--- stderr ---\n{proc.stderr}\n")
        detail = proc.stderr.strip() or proc.stdout.strip()
        try:
            err = json.loads(proc.stdout)
            detail = err.get("result") or err.get("error") or err.get("subtype") or detail
        except (json.JSONDecodeError, AttributeError):
            pass
        raise RuntimeError(f"claude exited with code {proc.returncode}: {str(detail)[:2000]}\n"
                           f"Full output saved to {run_dir / 'raw' / 'last_error.txt'}")
    try:
        response = json.loads(proc.stdout)
    except json.JSONDecodeError:
        response = {"result": proc.stdout}
    response["_elapsed_seconds"] = elapsed
    return response


def extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in Claude's answer")
    return json.loads(text[start:end + 1])


# ---------------------------------------------------------------- validation

def validate(phase: str, data: dict) -> list[str]:
    problems = []
    if data.get("phase") != phase:
        problems.append(f'"phase" should be "{phase}"')
    if phase in ("debt", "credit"):
        items = data.get("items")
        if not isinstance(items, list) or not items:
            return problems + ['"items" must be a non-empty list']
        for it in items:
            iid = it.get("id", "?")
            for k in ITEM_KEYS:
                if k not in it:
                    problems.append(f"{iid}: missing '{k}'")
            if it.get("kind") != phase:
                problems.append(f"{iid}: kind should be '{phase}'")
            if it.get("status") not in STATUS[phase]:
                problems.append(f"{iid}: status '{it.get('status')}' not in {sorted(STATUS[phase])}")
            if it.get("basis") not in ("observed", "inferred"):
                problems.append(f"{iid}: basis must be 'observed' or 'inferred'")
            for k in ("confidence_exists", "confidence_impact"):
                if it.get(k) not in LEVELS:
                    problems.append(f"{iid}: {k} must be low, medium or high")
            if it.get("footprint") not in ("small", "medium", "large"):
                problems.append(f"{iid}: footprint must be small, medium or large")
            freq = it.get("frequency") or {}
            if not {"all_history_commits", "window_commits", "method"} <= set(freq):
                problems.append(f"{iid}: frequency needs all_history_commits, window_commits and method")
            if not it.get("evidence"):
                problems.append(f"{iid}: evidence is empty")
            if phase == "credit" and "credit_test" not in it:
                problems.append(f"{iid}: missing 'credit_test'")
        if phase == "credit" and "pairs" not in data:
            problems.append('missing "pairs"')
    else:
        for k in ("verdict_window", "verdict_all_history"):
            if data.get(k) not in VERDICTS:
                problems.append(f"{k} must be one of {sorted(VERDICTS)}")
        for k in ("weighing_method", "key_items", "self_assessment", "method_feedback"):
            if k not in data:
                problems.append(f"missing '{k}'")
    if "self_check" not in data:
        problems.append('missing "self_check"')
    return problems


def repair_prompt(phase: str, answer: str, problems: list[str]) -> str:
    return (
        f"Your answer for the {phase} phase could not be accepted. Fix only these problems and return the "
        "corrected JSON object, with no prose and no code fences. Do not re-run the analysis; keep every "
        "finding as it is unless a problem requires changing it.\n\nProblems:\n- "
        + "\n- ".join(problems) + "\n\nYour previous answer:\n" + answer
    )


# ---------------------------------------------------------------- main

def run_phase(phase: str, run_dir: Path, repo: Path, inventory: dict, args) -> dict:
    raw = run_dir / "raw"
    raw.mkdir(exist_ok=True)
    prompt = build_prompt(phase, run_dir, inventory)
    (raw / f"{phase}.prompt.md").write_text(prompt)
    print(f"[{phase}] running claude (this can take several minutes) ...", file=sys.stderr)

    response = call_claude(prompt, repo, run_dir, args.tools, args.model, args.claude_arg)
    (raw / f"{phase}.response.json").write_text(json.dumps(response, indent=2))
    answer = response.get("result", "")
    entry = {"phase": phase, "elapsed_seconds": response.get("_elapsed_seconds"),
             "session_id": response.get("session_id"), "repaired": False}
    for key in ("total_cost_usd", "num_turns", "usage", "duration_ms"):
        if key in response:
            entry[key] = response[key]

    try:
        data = extract_json(answer)
        problems = validate(phase, data)
    except (ValueError, json.JSONDecodeError) as e:
        data, problems = None, [f"answer was not valid JSON: {e}"]

    if problems:
        print(f"[{phase}] {len(problems)} validation problem(s); asking Claude to repair the JSON ...", file=sys.stderr)
        fix = call_claude(repair_prompt(phase, answer, problems), repo, run_dir, "Read", args.model, args.claude_arg)
        (raw / f"{phase}.repair.response.json").write_text(json.dumps(fix, indent=2))
        entry["repaired"] = True
        try:
            data = extract_json(fix.get("result", ""))
            problems = validate(phase, data)
        except (ValueError, json.JSONDecodeError) as e:
            problems = [f"repaired answer was not valid JSON: {e}"]

    entry["validation_problems"] = problems
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True).stdout
    entry["repo_unchanged"] = status.strip() == ""
    if not entry["repo_unchanged"]:
        print(f"[{phase}] WARNING: the repository has uncommitted changes after this phase:\n{status}", file=sys.stderr)
    if data is not None:
        (run_dir / PHASES[phase]["out"]).write_text(json.dumps(data, indent=2))
        print(f"[{phase}] saved {PHASES[phase]['out']}"
              + (f" with {len(problems)} remaining problem(s)" if problems else ""), file=sys.stderr)
    else:
        print(f"[{phase}] FAILED: no usable JSON. See raw/{phase}.response.json", file=sys.stderr)
    return entry


def main():
    p = argparse.ArgumentParser(description="Phases 2-4 through Claude Code headless mode.")
    p.add_argument("run_dir", type=Path, help="folder containing inventory.json from metrics.py")
    p.add_argument("--repo", type=Path, help="path to the cloned repository (default: <run_dir>/repo)")
    p.add_argument("--phases", default="debt,credit,verdict", help="comma-separated subset of debt,credit,verdict")
    p.add_argument("--model", help="model name passed to claude --model")
    p.add_argument("--tools", default=DEFAULT_TOOLS, help="value for claude --allowedTools")
    p.add_argument("--skip-existing", action="store_true", help="skip phases whose output file already exists")
    p.add_argument("--claude-arg", action="append", default=[], help="extra argument passed to claude (repeatable)")
    args = p.parse_args()

    run_dir = args.run_dir
    inventory_path = run_dir / "inventory.json"
    if not inventory_path.exists():
        sys.exit(f"{inventory_path} not found. Run metrics.py first.")
    inventory = json.loads(inventory_path.read_text())
    repo = (args.repo or run_dir / "repo").expanduser().resolve()
    if not (repo / ".git").exists():
        sys.exit(f"No git repository at {repo}. Pass --repo /path/to/clone.")

    phases = [x.strip() for x in args.phases.split(",") if x.strip()]
    for ph in phases:
        if ph not in PHASES:
            sys.exit(f"Unknown phase '{ph}'. Choose from {', '.join(PHASES)}.")

    log_path = run_dir / "run_log.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else {"runs": []}
    run = {
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "claude_version": claude_version(),
        "model": args.model or "default",
        "allowed_tools": args.tools,
        "head_commit": inventory["meta"]["head_commit"],
        "phases": [],
    }
    for ph in phases:
        if args.skip_existing and (run_dir / PHASES[ph]["out"]).exists():
            print(f"[{ph}] output exists, skipping", file=sys.stderr)
            continue
        if ph == "credit" and not (run_dir / PHASES["debt"]["out"]).exists():
            sys.exit("The credit phase needs 02-debt.json. Run the debt phase first.")
        if ph == "verdict" and not (run_dir / PHASES["credit"]["out"]).exists():
            sys.exit("The verdict phase needs 03-credit.json. Run the credit phase first.")
        entry = run_phase(ph, run_dir, repo, inventory, args)
        run["phases"].append(entry)
        log_path.write_text(json.dumps({"runs": log["runs"] + [run]}, indent=2))  # save progress after each phase
    run["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    log["runs"].append(run)
    log_path.write_text(json.dumps(log, indent=2))
    print(f"Done. Log: {log_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
