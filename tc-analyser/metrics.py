#!/usr/bin/env python3
"""
Phase 1 of the technical debt / technical credit PoC: measurable facts only.

No AI is used here. Every number comes from git or from parsing tracked files,
so the same commit always gives the same output. Each metric records the method
used to compute it, so results can be reproduced and checked.

Usage:
    python metrics.py https://github.com/ultralytics/yolov5      # clones into runs/<name>/repo
    python metrics.py /path/to/local/repo                       # uses an existing clone
    python metrics.py <url-or-path> --out runs/yolov5

Output:
    <out>/inventory.json   machine-readable facts for later phases and charts
    <out>/inventory.md     short human-readable summary

Requires Python 3.9+ and git. No third-party packages.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCHEMA_VERSION = "1.0"
TOP_N = 15
WINDOW_MONTHS = 24  # fixed window, measured back from the HEAD commit date (not from today)

SATD_KEYWORDS = ["TODO", "FIXME", "HACK", "XXX", "workaround", "deprecated"]
SATD_RE = re.compile(r"\b(" + "|".join(SATD_KEYWORDS) + r")\b", re.IGNORECASE)

LANG_EXT = {"python": {".py"}, "java": {".java"}}
BOT_RE = re.compile(r"\[bot\]|\bbot$", re.IGNORECASE)


# ---------------------------------------------------------------- git helpers

def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def clone(url: str, dest: Path) -> Path:
    if (dest / ".git").exists():
        print(f"Using existing clone at {dest}", file=sys.stderr)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Cloning {url} (full history) ...", file=sys.stderr)
    subprocess.run(["git", "clone", url, str(dest)], check=True)
    return dest


def tracked_files(repo: Path) -> list[str]:
    return [f for f in git(repo, "ls-files", "-z").split("\0") if f]


def read_text(repo: Path, rel: str) -> str | None:
    try:
        return (repo / rel).read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------- metrics

def meta(repo: Path, source: str) -> dict:
    head = git(repo, "rev-parse", "HEAD").strip()
    head_date = git(repo, "log", "-1", "--format=%cs").strip()
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    since = window_start(head_date)
    return {
        "schema_version": SCHEMA_VERSION,
        "source": source,
        "head_commit": head,
        "head_short": head[:8],
        "head_date": head_date,
        "branch": branch,
        "window": {"name": f"last_{WINDOW_MONTHS}_months", "since": since, "until": head_date,
                   "note": "Window is measured back from the HEAD commit date, so reruns give the same result."},
        "analysed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "has_mailmap": (repo / ".mailmap").exists(),
    }


def window_start(head_date: str) -> str:
    d = dt.date.fromisoformat(head_date)
    month = d.month - WINDOW_MONTHS % 12
    year = d.year - WINDOW_MONTHS // 12
    if month <= 0:
        month += 12
        year -= 1
    day = min(d.day, 28)
    return dt.date(year, month, day).isoformat()


def detect_language(files: list[str]) -> dict:
    counts = {lang: sum(1 for f in files if Path(f).suffix in exts) for lang, exts in LANG_EXT.items()}
    primary = max(counts, key=counts.get) if any(counts.values()) else "unknown"
    return {"primary": primary, "file_counts": counts,
            "method": "count of git-tracked files by extension (.py, .java)"}


def history(repo: Path, since: str) -> dict:
    def count(*extra):
        return int(git(repo, "rev-list", "--count", *extra, "HEAD").strip())

    authors = [a for a in git(repo, "log", "--format=%aN").splitlines() if a]
    unique = sorted(set(authors))
    bots = [a for a in unique if BOT_RE.search(a)]
    dates = git(repo, "log", "--reverse", "--format=%as").splitlines()
    top = Counter(authors).most_common(5)
    return {
        "commits": {"all": count(), "window": count(f"--since={since}")},
        "merges": {"all": count("--merges"), "window": count("--merges", f"--since={since}")},
        "authors": {"distinct_names": len(unique), "bots": bots, "top_5": top},
        "first_commit_date": dates[0] if dates else None,
        "last_commit_date": dates[-1] if dates else None,
        "method": "git rev-list --count HEAD [--since]; git log --format=%aN (uses .mailmap if present)",
    }


def size(repo: Path, files: list[str], lang: str) -> dict:
    exts = LANG_EXT.get(lang, set())
    rows = []
    for f in files:
        if Path(f).suffix not in exts:
            continue
        text = read_text(repo, f)
        if text is None:
            continue
        lines = text.splitlines()
        rows.append((f, len(lines), sum(1 for l in lines if l.strip())))
    rows.sort(key=lambda r: r[1], reverse=True)
    return {
        "source_files": len(rows),
        "lines_total": sum(r[1] for r in rows),
        "lines_non_blank": sum(r[2] for r in rows),
        "largest_files": [{"file": f, "lines": n} for f, n, _ in rows[:TOP_N]],
        "method": f"line counts of git-tracked {', '.join(sorted(exts)) or 'source'} files",
    }


def churn(repo: Path, since: str | None, existing: set[str]) -> dict:
    """Commits and distinct authors per file, from one pass over the log."""
    args = ["log", "--format=@@%aN", "--name-only", "--no-renames"]
    if since:
        args.append(f"--since={since}")
    commits_per_file: Counter = Counter()
    authors_per_file: dict[str, Counter] = defaultdict(Counter)
    author = None
    for line in git(repo, *args).splitlines():
        if line.startswith("@@"):
            author = line[2:]
        elif line.strip():
            commits_per_file[line] += 1
            authors_per_file[line][author] += 1
    rows = []
    for f, n in commits_per_file.most_common(TOP_N):
        a = authors_per_file[f]
        top_author, top_count = a.most_common(1)[0]
        rows.append({
            "file": f, "commits": n, "distinct_authors": len(a),
            "top_author": top_author, "top_author_share": round(top_count / n, 2),
            "still_exists": f in existing,
        })
    return {"top_files": rows,
            "method": "git log --format=@@%aN --name-only --no-renames" + (f" --since={since}" if since else ""),
            "note": "Per path, renames not followed: a renamed file's history is split across its old and new names."}


def comment_lines(text: str, lang: str) -> list[tuple[int, str]]:
    out = []
    if lang == "python":
        import io
        import tokenize
        try:
            for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                if tok.type == tokenize.COMMENT:
                    out.append((tok.start[0], tok.string))
            return out
        except (tokenize.TokenError, IndentationError, SyntaxError):
            out = []  # fall back to a line-based scan for files that don't tokenize
            for i, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    out.append((i, line.strip()))
            return out
    in_block = False
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if in_block:
            out.append((i, s))
            if "*/" in s:
                in_block = False
        elif s.startswith("/*"):
            out.append((i, s))
            in_block = "*/" not in s
        else:
            m = re.search(r"(?<!:)//", line)  # skip the // inside URLs such as http://
            if m:
                out.append((i, line[m.start():]))
    return out


def satd(repo: Path, files: list[str], lang: str) -> dict:
    exts = LANG_EXT.get(lang, set())
    per_file: Counter = Counter()
    per_keyword: Counter = Counter()
    examples = []
    annotations = Counter()
    for f in files:
        if Path(f).suffix not in exts:
            continue
        text = read_text(repo, f)
        if text is None:
            continue
        for ln, c in comment_lines(text, lang):
            for m in SATD_RE.finditer(c):
                kw = m.group(1).upper() if m.group(1).isupper() else m.group(1).lower()
                per_keyword[kw] += 1
                per_file[f] += 1
                if len(examples) < 10:
                    examples.append({"file": f, "line": ln, "text": c.strip()[:160]})
        if lang == "java":
            annotations["@Deprecated"] += len(re.findall(r"@Deprecated\b", text))
            annotations["@SuppressWarnings"] += len(re.findall(r"@SuppressWarnings\b", text))
    result = {
        "total": sum(per_keyword.values()),
        "by_keyword": dict(per_keyword),
        "top_files": [{"file": f, "count": n} for f, n in per_file.most_common(TOP_N)],
        "examples": examples,
        "method": "whole-word, case-insensitive match of " + ", ".join(SATD_KEYWORDS) + " inside comments only",
        "note": "Keyword matching undercounts: comments that describe a workaround in other words are missed. Later phases look for those.",
    }
    if lang == "java":
        result["annotations"] = dict(annotations)
    return result


def tests(repo: Path, files: list[str], lang: str, source_files: int) -> dict:
    if lang == "python":
        test_files = [f for f in files if f.endswith(".py") and (
            Path(f).name.startswith("test_") or Path(f).name.endswith("_test.py") or "/tests/" in f"/{f}")]
        pattern = re.compile(r"^\s*(async\s+)?def\s+test_", re.MULTILINE)
        method = "files named test_*.py, *_test.py or under tests/; count of 'def test_'"
    elif lang == "java":
        test_files = [f for f in files if f.endswith(".java") and (
            "src/test/" in f or re.search(r"(Test|Tests|IT)\.java$", f))]
        pattern = re.compile(r"@Test\b")
        method = "files under src/test/ or named *Test.java, *Tests.java, *IT.java; count of @Test"
    else:
        return {"test_files": 0, "test_functions": 0, "method": "unknown language"}
    functions = sum(len(pattern.findall(read_text(repo, f) or "")) for f in test_files)
    non_test = source_files - len(test_files)
    return {
        "test_files": len(test_files),
        "test_functions": functions,
        "non_test_source_files": non_test,
        "test_files_per_source_file": round(len(test_files) / non_test, 3) if non_test > 0 else None,
        "method": method,
    }


def ci(repo: Path, files: list[str]) -> dict:
    workflows = [f for f in files if f.startswith(".github/workflows/") and f.endswith((".yml", ".yaml"))]
    other = [f for f in files if f in {".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml", ".travis.yml"}
             or f.startswith(".circleci/")]
    test_cmd = re.compile(r"\b(pytest|python -m pytest|unittest|tox|nox|mvn\b.*\b(test|verify)|gradlew?\b.*\b(test|check|build))")
    uses = re.compile(r"uses:\s*([^\s#]+)")
    sha = re.compile(r"@[0-9a-f]{40}$")
    rows, refs = [], Counter()
    for f in workflows:
        text = read_text(repo, f) or ""
        actions = uses.findall(text)
        for a in actions:
            if a.startswith("./"):
                refs["local"] += 1
            elif sha.search(a):
                refs["pinned_sha"] += 1
            elif re.search(r"@(main|master)$", a):
                refs["branch"] += 1
            else:
                refs["tag"] += 1
        rows.append({"file": f, "runs_tests": bool(test_cmd.search(text)), "action_refs": len(actions)})
    return {
        "github_workflows": rows,
        "other_ci_files": other,
        "workflows_running_tests": sum(r["runs_tests"] for r in rows),
        "action_ref_pinning": dict(refs),
        "method": "tracked files under .github/workflows; regex for test commands and 'uses:' references",
    }


# ---------------------------------------------------------------- dependencies

PY_SPEC = re.compile(r"^\s*([A-Za-z0-9_.\-\[\]]+)\s*(.*)$")


def classify_python_spec(spec: str) -> str:
    spec = spec.split(";")[0].strip()  # drop environment markers
    if not spec:
        return "open"
    if spec.startswith("==") and "*" not in spec and "," not in spec:
        return "exact"
    if "<" in spec or "~=" in spec or "==" in spec:
        return "bounded"
    if ">" in spec:
        return "minimum_only"
    return "other"


def python_deps(repo: Path, files: list[str]) -> dict:
    specs = []
    sources = []
    for f in files:
        name = Path(f).name
        if re.match(r"requirements.*\.txt$", name):
            sources.append(f)
            for line in (read_text(repo, f) or "").splitlines():
                line = line.split("#")[0].strip()
                if not line or line.startswith(("-", "git+", "http")):
                    continue
                m = PY_SPEC.match(line)
                if m:
                    specs.append({"source": f, "name": m.group(1), "spec": m.group(2).strip(),
                                  "class": classify_python_spec(m.group(2))})
    if "pyproject.toml" in files:
        sources.append("pyproject.toml")
        data = load_toml(repo / "pyproject.toml")
        project = data.get("project", {}) if data else {}
        entries = list(project.get("dependencies", []))
        for group in project.get("optional-dependencies", {}).values():
            entries += group
        for e in entries:
            m = PY_SPEC.match(e)
            if m:
                specs.append({"source": "pyproject.toml", "name": m.group(1), "spec": m.group(2).strip(),
                              "class": classify_python_spec(m.group(2))})
    locks = [f for f in files if Path(f).name in {"poetry.lock", "uv.lock", "Pipfile.lock", "pdm.lock"}]
    names = Counter(s["name"].lower().split("[")[0] for s in specs)
    return {
        "sources": sources,
        "specs": len(specs),
        "by_class": dict(Counter(s["class"] for s in specs)),
        "declared_in_more_than_one_place": sorted(n for n, c in names.items() if c > 1),
        "lock_files": locks,
        "method": "parse requirements*.txt and pyproject.toml [project] dependencies; classify each version specifier",
    }


def load_toml(path: Path) -> dict | None:
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        return None
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def java_deps(repo: Path, files: list[str]) -> dict:
    poms = [f for f in files if Path(f).name == "pom.xml"]
    gradles = [f for f in files if Path(f).name in {"build.gradle", "build.gradle.kts"}]
    by_class: Counter = Counter()
    count = 0
    for f in poms:
        text = read_text(repo, f) or ""
        for dep in re.findall(r"<dependency>(.*?)</dependency>", text, re.DOTALL):
            count += 1
            v = re.search(r"<version>(.*?)</version>", dep)
            if not v:
                by_class["managed_or_inherited"] += 1
            elif "SNAPSHOT" in v.group(1):
                by_class["snapshot"] += 1
            elif v.group(1).startswith("${"):
                by_class["property"] += 1
            elif re.search(r"[\[\(,]", v.group(1)):
                by_class["range"] += 1
            else:
                by_class["exact"] += 1
    for f in gradles:
        text = read_text(repo, f) or ""
        for m in re.finditer(r"""(implementation|api|compileOnly|runtimeOnly|testImplementation)\s*\(?\s*["']([^"']+)["']""", text):
            count += 1
            coord = m.group(2)
            parts = coord.split(":")
            if len(parts) < 3:
                by_class["managed_or_inherited"] += 1
            elif "+" in parts[2] or "latest" in parts[2]:
                by_class["dynamic"] += 1
            elif "SNAPSHOT" in parts[2]:
                by_class["snapshot"] += 1
            else:
                by_class["exact"] += 1
    locks = [f for f in files if Path(f).name in {"gradle.lockfile"} or f.endswith("/gradle.lockfile")]
    return {
        "sources": poms + gradles,
        "specs": count,
        "by_class": dict(by_class),
        "lock_files": locks,
        "method": "regex over pom.xml <dependency> blocks and Gradle dependency declarations",
    }


# ---------------------------------------------------------------- documentation

def python_docstrings(repo: Path, files: list[str]) -> dict:
    counts = {"functions": [0, 0], "classes": [0, 0], "modules": [0, 0]}
    for f in files:
        if not f.endswith(".py"):
            continue
        try:
            tree = ast.parse(read_text(repo, f) or "")
        except SyntaxError:
            continue
        counts["modules"][1] += 1
        counts["modules"][0] += bool(ast.get_docstring(tree))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                key = "functions"
            elif isinstance(node, ast.ClassDef):
                key = "classes"
            else:
                continue
            counts[key][1] += 1
            counts[key][0] += bool(ast.get_docstring(node))
    return {k: {"with_docstring": a, "total": b, "share": round(a / b, 3) if b else None}
            for k, (a, b) in counts.items()}


def java_javadoc(repo: Path, files: list[str]) -> dict:
    total = documented = 0
    method_re = re.compile(r"^\s*public\s+[\w<>\[\],\s]+\s+\w+\s*\([^;]*$")
    for f in files:
        if not f.endswith(".java") or "src/test/" in f:
            continue
        lines = (read_text(repo, f) or "").splitlines()
        for i, line in enumerate(lines):
            if method_re.match(line) and " class " not in line:
                total += 1
                j = i - 1
                while j >= 0 and lines[j].strip().startswith("@"):
                    j -= 1
                documented += j >= 0 and lines[j].strip().endswith("*/")
    return {"public_methods": {"with_javadoc": documented, "total": total,
                               "share": round(documented / total, 3) if total else None},
            "note": "Approximate: regex-based detection of public method declarations."}


def docs(repo: Path, files: list[str], lang: str) -> dict:
    readmes = [f for f in files if Path(f).name.lower().startswith("readme")]
    adr_dirs = sorted({str(Path(f).parent) for f in files
                       if re.search(r"(^|/)(adr|adrs|decisions)(/|$)", str(Path(f).parent), re.IGNORECASE)})
    adr_files = [f for f in files if any(f.startswith(d + "/") for d in adr_dirs) and f.endswith(".md")]
    agent_docs = [f for f in files if Path(f).name in {"CLAUDE.md", "AGENTS.md", "CONTRIBUTING.md"}]
    result = {
        "readme_files": readmes,
        "has_docs_folder": any(f.startswith(("docs/", "doc/")) for f in files),
        "adr_directories": adr_dirs,
        "adr_count": len(adr_files),
        "contributor_and_agent_docs": agent_docs,
    }
    if lang == "python":
        result["docstrings"] = python_docstrings(repo, files)
    elif lang == "java":
        result["javadoc"] = java_javadoc(repo, files)
    return result


# ---------------------------------------------------------------- output

def to_markdown(inv: dict) -> str:
    m, h, s, t, d = inv["meta"], inv["history"], inv["size"], inv["tests"], inv["dependencies"]
    lines = [
        f"# Inventory: {m['source']}",
        "",
        f"Commit `{m['head_short']}` ({m['head_date']}), branch `{m['branch']}`. "
        f"Primary language: {inv['language']['primary']}. Window: {m['window']['since']} to {m['window']['until']}.",
        "",
        "| Metric | All history | Window |",
        "|---|---|---|",
        f"| Commits | {h['commits']['all']} | {h['commits']['window']} |",
        f"| Merges | {h['merges']['all']} | {h['merges']['window']} |",
        f"| Distinct author names | {h['authors']['distinct_names']} | |",
        "",
        f"Source files: {s['source_files']}, lines: {s['lines_total']} ({s['lines_non_blank']} non-blank).",
        f"Tests: {t.get('test_files')} files, {t.get('test_functions')} test functions.",
        f"Debt-marker comments: {inv['satd']['total']} {inv['satd']['by_keyword']}.",
        f"Dependencies: {d['specs']} specs {d['by_class']}; lock files: {d['lock_files'] or 'none'}.",
        f"CI workflows: {len(inv['ci']['github_workflows'])}, running tests: {inv['ci']['workflows_running_tests']}; "
        f"action refs: {inv['ci']['action_ref_pinning']}.",
        "",
        "## Largest files",
        *[f"- {r['file']}: {r['lines']}" for r in s["largest_files"]],
        "",
        "## Most-changed files (all history)",
        *[f"- {r['file']}: {r['commits']} commits, {r['distinct_authors']} authors"
          + ("" if r["still_exists"] else " (no longer exists)") for r in inv["churn"]["all"]["top_files"]],
        "",
        "## Most-changed files (window)",
        *[f"- {r['file']}: {r['commits']} commits, {r['distinct_authors']} authors"
          for r in inv["churn"]["window"]["top_files"]],
        "",
    ]
    return "\n".join(lines)


def run(target: str, out: Path | None) -> Path:
    if re.match(r"^(https?://|git@)", target):
        name = re.sub(r"\.git$", "", target.rstrip("/").split("/")[-1])
        out = out or Path("runs") / name
        repo = clone(target, out / "repo")
    else:
        repo = Path(target).expanduser().resolve()
        out = out or Path("runs") / repo.name
    out.mkdir(parents=True, exist_ok=True)

    files = tracked_files(repo)
    existing = set(files)
    m = meta(repo, target)
    lang = detect_language(files)
    primary = lang["primary"]
    sz = size(repo, files, primary)

    inventory = {
        "meta": m,
        "language": lang,
        "history": history(repo, m["window"]["since"]),
        "size": sz,
        "churn": {"all": churn(repo, None, existing), "window": churn(repo, m["window"]["since"], existing)},
        "satd": satd(repo, files, primary),
        "tests": tests(repo, files, primary, sz["source_files"]),
        "ci": ci(repo, files),
        "dependencies": python_deps(repo, files) if primary == "python" else java_deps(repo, files),
        "docs": docs(repo, files, primary),
    }
    (out / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    (out / "inventory.md").write_text(to_markdown(inventory), encoding="utf-8")
    print(f"Wrote {out / 'inventory.json'} and {out / 'inventory.md'}", file=sys.stderr)
    return out


def main():
    p = argparse.ArgumentParser(description="Phase 1: measurable repository facts (no AI).")
    p.add_argument("target", help="GitHub URL or path to a local clone")
    p.add_argument("--out", type=Path, help="output folder (default: runs/<repo-name>)")
    args = p.parse_args()
    run(args.target, args.out)


if __name__ == "__main__":
    main()
