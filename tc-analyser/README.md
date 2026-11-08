# tc-analyser: technical debt and technical credit analysis

A proof of concept that takes a GitHub repository and produces an analysis of its **technical debt** and **technical credit**, ending in a self-contained HTML report.

- **Technical debt:** a shortcut or sub-optimal choice that makes future change more expensive. The recurring extra cost is the "interest".
- **Technical credit** (Gorton, Bucaioni and Pelliccione, CACM): a design decision that cost more up front but makes future change cheaper. Credit counts as *realised* only once it has actually been used; an investment that is never used may be over-engineering.

The tool automates a four-phase method first run by hand on `ultralytics/yolov5`.

---

## Contents

1. [How it works](#how-it-works)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Running an analysis](#running-an-analysis)
5. [What a run produces](#what-a-run-produces)
6. [Useful options](#useful-options)
7. [Troubleshooting](#troubleshooting)
8. [Time and cost](#time-and-cost)
9. [Design choices](#design-choices)
10. [Project structure](#project-structure)
11. [Customising the analysis](#customising-the-analysis)
12. [Results so far](#results-so-far)
13. [Known limitations](#known-limitations)
14. [Sharing the PoC](#sharing-the-poc)

---

## How it works

```
GitHub URL or local clone
        │
        ▼
  metrics.py ─────────────►  inventory.json      Phase 1: measured facts, no AI
        │
        ▼
  run_claude.py
    ├─ debt phase    ─────►  02-debt.json        Phase 2
    ├─ credit phase  ─────►  03-credit.json      Phase 3 (reads Phase 2)
    └─ verdict phase ─────►  04-verdict.json     Phase 4 (reads Phases 2 and 3)
        │
        ▼
  report.py ──────────────►  report.html         charts, tables and run statistics
```

`analyse.py` runs all three steps in order. Each step reads only the files the earlier steps wrote, so you can stop after any step, inspect its output, and resume.

**Phase 1, measurement (`metrics.py`).** Clones the repository with its full history and measures it with git and file parsing: commits, size, the largest and most-changed files, debt-marker comments (TODO, FIXME and similar), tests, CI workflows, dependency pinning, and documentation. It detects whether the repository is mainly Python or Java and uses matching checks. No AI is involved, so the same commit always gives the same numbers.

**Phases 2 to 4, interpretation (`run_claude.py`).** Runs Claude Code in headless mode (`claude -p`), once per phase:

- **Debt:** the most significant debt, with evidence, how often its interest is paid, and how much of the codebase it affects.
- **Credit:** the most significant credit, an explicit credit test, measured cash-in, and credit-debt pairs.
- **Verdict:** two verdicts on a five-point scale (one for the last 24 months, one for all history), a self-assessment, and suggestions for improving the method.

Each phase is a separate Claude Code process with read-only tools. Its answer must follow a fixed JSON shape, which the script checks before saving.

**Report (`report.py`).** Turns the saved files into one HTML file with the verdict, a ledger of all findings, expandable tables with evidence, credit-debt pairs, charts, the self-assessment, and run statistics. It needs no internet connection.

---

## Prerequisites

| Requirement | Check with | Notes |
|---|---|---|
| macOS, Linux, or Windows with WSL | | |
| Python 3.9 or newer | `python3 --version` | Python 3.11+ also reads dependencies from `pyproject.toml` |
| Git | `git --version` | needed to clone and read history |
| Claude Code | `claude --version` | install guide: https://code.claude.com/docs/en/setup |
| A Claude plan that includes Claude Code | `claude`, then `/login` | Pro, Max, Team or Enterprise |

No extra Python packages are needed. Analysing Java repositories does not require Java, because the tool only reads the code.

### Installing Claude Code (macOS, Linux, WSL)

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

If the installer says `~/.local/bin` is not in your PATH, run the command it prints, for example:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
```

Then log in once:

```bash
claude        # opens Claude Code; type /login, approve in the browser, then /exit
```

---

## Installation

```bash
mkdir -p ~/ra-tech-credit
cd ~/ra-tech-credit
unzip ~/Downloads/tc-analyser.zip
cd tc-analyser
ls
```

You should see `analyse.py`, `metrics.py`, `run_claude.py`, `report.py`, `prompts/` and this `README.md`.

**Updating to a new version:** delete the old zip in Downloads first, so the browser doesn't save the new one as `tc-analyser (1).zip`, then unzip with `-o` to overwrite. Your `runs/` folder is never included in the zip, so existing results are kept.

```bash
cd ~/ra-tech-credit
unzip -o ~/Downloads/tc-analyser.zip
```

---

## Running an analysis

### 1. Check that Claude Code is logged in

```bash
claude -p --output-format json "Reply with the word ok"
```

If the output contains `"is_error":false`, you are ready. If it says the OAuth session expired, run `claude`, type `/login`, approve in the browser, then `/exit`.

### 2. Run the analysis

```bash
cd ~/ra-tech-credit/tc-analyser
python3 analyse.py https://github.com/OWNER/REPO --open
```

What you will see:

1. **Phase 1** (under a minute): the clone, then `Wrote runs/REPO/inventory.json`.
2. **Phases 2 to 4** (about 15 to 20 minutes): `[debt] running claude ...`, then the same for credit and verdict. The terminal stays quiet while each phase works; this is normal.
3. **Report** (about a second): `Wrote runs/REPO/report.html`, and the report opens in your browser.

Keep the terminal open and don't let the computer sleep during the run.

### 3. Open the report later

```bash
open runs/REPO/report.html          # macOS
xdg-open runs/REPO/report.html      # Linux
```

---

## What a run produces

Everything is saved in `runs/REPO/`:

| File | Contents |
|---|---|
| `report.html` | the report; open it in any browser |
| `inventory.json`, `inventory.md` | Phase 1 measured facts, each with the method used |
| `02-debt.json` | debt findings |
| `03-credit.json` | credit findings and credit-debt pairs |
| `04-verdict.json` | verdicts, self-assessment and method feedback |
| `run_log.json` | Claude Code version, model, allowed tools, commit, time, turns, cost estimate, validation results, and whether the repository stayed unchanged |
| `raw/<phase>.prompt.md` | the exact prompt sent to Claude |
| `raw/<phase>.response.json` | Claude's full answer, with token usage and session ID |
| `raw/last_error.txt` | only if a phase failed: Claude Code's full error output |
| `repo/` | the cloned repository (URL mode only) |

### What each finding contains

Every debt and credit item follows the same shape:

- `id`, `kind`, `category`, `title`, `description`
- `decision_id`: the design decision it comes from. Debt and credit with the same decision form a pair.
- `evidence`: files, line ranges and commits
- `basis`: `observed` (seen directly) or `inferred` (Claude's interpretation)
- `confidence_exists` and `confidence_impact`: low, medium or high
- `status`: for debt `realised` or `potential`; for credit `realised`, `potential` or `over_engineering`
- `frequency`: commit counts for all history and for the window, with the command used
- `footprint`: small, medium or large
- `impact`: the interest (debt) or measured cash-in (credit)
- `credit_test` (credit only): extra cost up front, whether it makes change cheaper, and any before-and-after comparison

---

## Useful options

| Goal | Command |
|---|---|
| Resume an interrupted run | `python3 analyse.py <url> --skip-existing` |
| Analyse a repository you already cloned | `python3 analyse.py ~/path/to/repo --name REPO` |
| Run one Claude phase | `python3 run_claude.py runs/REPO --phases debt` |
| Run several phases | `python3 run_claude.py runs/REPO --phases credit,verdict` |
| Use a specific model | add `--model <name>` |
| Only measure (no AI) | `python3 metrics.py <url-or-path> --out runs/REPO` |
| Rebuild only the report | `python3 report.py runs/REPO --open` |

Phases must run in order: credit needs `02-debt.json`, and the verdict needs `03-credit.json`.

### Starting a run from scratch

To rerun a repository completely, for example for a demo, rename its run folder rather than deleting it, so you keep the old results as a backup:

```bash
mv runs/REPO runs/REPO-backup
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Failed to authenticate: OAuth session expired` | run `claude`, type `/login`, then `/exit` |
| `claude: command not found` | add `~/.local/bin` to your PATH (see Prerequisites), then open a new terminal |
| `No such file or directory` for a `.py` file | you are in the wrong folder, or unzipped an old version; check with `ls` |
| A phase fails with `claude exited with code 1` | read `runs/REPO/raw/last_error.txt`, fix the cause, rerun with `--skip-existing` |
| `validation_problems` listed in `run_log.json` | Claude's answer didn't fully match the JSON shape even after one repair attempt; the file is still saved, but check the listed fields |
| `repo_unchanged: false` in `run_log.json` | the repository has uncommitted changes after a phase; inspect with `git status` in `runs/REPO/repo` |
| A phase runs for more than 45 minutes | the script stops it automatically; check `raw/last_error.txt` and rerun |

---

## Time and cost

Measured on `ultralytics/yolov5` (3,044 commits, 52 Python files):

| Phase | Time | Turns | Claude Code cost estimate |
|---|---|---|---|
| Phase 1 (script) | under 1 min | | none |
| Debt | 8.6 min | 80 | $2.27 |
| Credit | 8.5 min | 86 | $2.84 |
| Verdict | 1.9 min | 10 | $0.78 |
| **Total** | **about 19 min** | **176** | **about $5.89** |

Cost figures are Claude Code's own estimates and may differ from actual billing on a subscription or organisation plan. Smaller repositories are usually faster. The verdict phase is cheap because it mostly reads the saved phase files.

---

## Design choices

| Choice | Problem it solves |
|---|---|
| Phase 1 as a plain script | Measurement needs no judgment; a script gives identical results on every run, at no cost |
| One Claude process per phase | Each phase starts in a fresh session and only sees the saved files |
| Read-only tools | Claude can use Read, Grep, Glob, `wc`, `ls` and read-only git subcommands (`log`, `show`, `grep`, `ls-files`, `rev-list`, `rev-parse`, `blame`, `diff`, `shortlog`, `cat-file`). It has no write tools, and commands such as `git checkout` are not allowed. `git status` is checked after every phase |
| Two fixed time windows | All history, and the 24 months before the HEAD commit date. Counting back from the commit rather than from today makes reruns identical. The verdict depends strongly on the window, so it is fixed in advance |
| Decision IDs | Debt and credit from the same decision share an ID, so pairs are found automatically and no decision is counted twice |
| Split confidence | Separate confidence for whether an item exists and for how much it matters |
| Explicit credit test | Extra cost up front, makes change cheaper (not just a user feature), and a before-and-after comparison |
| Self-check | Each phase re-derives every number it quotes and backs every "none" or "all" claim with a command |
| Fixed JSON shape with validation | Results are comparable across repositories and can be charted; one automatic repair attempt, remaining problems logged |
| Everything recorded | Prompts, responses, versions, timings and costs are saved, so every result can be audited and reproduced |

---

## Project structure

```
tc-analyser/
  analyse.py          one command for the whole pipeline
  metrics.py          Phase 1: measurement, no AI
  run_claude.py       Phases 2-4: runs Claude Code headless and validates the answers
  report.py           builds runs/<repo>/report.html
  prompts/
    common.md         shared definitions, rules and output format for every phase
    02-debt.md        debt task, categories and JSON shape
    03-credit.md      credit task, credit test, pairs and JSON shape
    04-verdict.md     verdict, self-assessment and method feedback
  runs/               one folder per analysed repository (created on first run)
  README.md
```

---

## Customising the analysis

### Changing the prompts

Edit the files in `prompts/`. `common.md` holds the definitions and rules shared by every phase; each phase file holds its task and required JSON shape. Placeholders such as `{head_short}`, `{window_since}` and `{inventory_path}` are filled in automatically.

If you change the JSON shape, update the matching checks in `validate()` in `run_claude.py`.

Keep a record of each prompt version and its results (a prompt engineering log). Run a new version into a separate folder, for example `--name yolov5-v2`, so you can compare versions.

### Python and Java categories

The language detected in Phase 1 decides which domain categories are added to the prompts:

- **Python:** machine-learning debt (glue code, pipeline jungles, dead experimental paths, configuration debt, hidden data dependencies; Sculley et al., 2015) and machine-learning credit (reproducibility, experiment tracking, cheap experiment configuration, tools such as automatic batch sizing or hyperparameter search).
- **Java:** distributed-systems debt (error-handling shortcuts, concurrency workarounds, hardcoded configuration, missing retries or timeouts) and distributed-systems credit (resilience patterns, observability, versioned APIs, externalised configuration).

These live in the `DOMAIN` dictionary in `run_claude.py`.

### Changing the time window

Set `WINDOW_MONTHS` in `metrics.py` (default 24). Rerun Phase 1 and all later phases afterwards, since the prompts use the window from the inventory.

---

## Results so far

**YOLOv5, commit `794e40d9` (20 Oct 2026):**

- **Phase 1 validated.** The script reproduced the manual Phase 1 inventory exactly for commits, files, lines, largest and most-changed files, tests, dependencies, CI and docstrings. Two small differences (debt-marker comments 6 vs 7, authors on `train.py` 67 vs 64) come from documented method differences.
- **Verdicts.** Last 24 months: *leaning debt*, the same as the manual analysis. All history: *balanced*, one step from the manual *leaning credit*.
- **Findings.** 14 debt items and 13 credit items, with 5 credit-debt pairs. The central findings match the manual run: copied detect/segment/classify scripts as the main debt, the shared inference layer (`DetectMultiBackend`) as the strongest credit.
- **Time-window effect.** Most architectural credit shows no cash-in in the last 24 months (it paid off earlier), while nearly every debt item charges interest in that window.

---

## Known limitations

- **"Realised" debt is too generous in prompt v1.** All 14 YOLOv5 debt items were marked realised. Claude tends to count any commit touching the affected files as interest paid.
- **Bot commits may inflate credit.** Auto-formatting and Dependabot commits were counted as cash-in.
- **Over-engineering is under-reported.** The automated run found none; the manual run found five candidates.
- **Claude doesn't run the code.** Bugs are found by reading, so some suspicions can't be settled.
- **Run-to-run consistency is not yet measured.** Each repository should be analysed at least twice.
- **Weighing is still judgment.** The verdict weighs items by status, frequency, footprint and confidence, but not yet with a fixed numeric formula.
- **Authentication.** Headless runs need a valid Claude Code login; a long unattended batch would need a stable setup such as an API key.

### Planned for prompt v2

These come from Claude's own method feedback in the verdict phase:

1. Split every frequency into raw matches and commits actually classified as interest or cash-in, listing excluded commits.
2. Give each commit exactly one role, with a commit-to-decision map.
3. Use a fixed numeric weighting formula for the verdict.
4. Stop using raw file churn as interest, and compare hotspots with a per-repository baseline.
5. In Phase 1, classify CI workflows by what they run and count bot commits.

---

## Sharing the PoC

### Package the tool with results

From the folder above `tc-analyser`, package the tool and finished runs, leaving out cloned repositories (large, and easy to re-download):

```bash
cd ~/ra-tech-credit
zip -r tc-analyser-share.zip tc-analyser -x "*/repo/*" "*/__pycache__/*" "*/.DS_Store"
ls -lh tc-analyser-share.zip
```

Remove any backup run folders first if you don't want them included.

### Share in Microsoft Teams

1. Open the chat, click the **paperclip** (Attach) below the message box, choose **Upload from this device**, and select the zip.
2. Recipients download it, unzip it, and open `runs/<repo>/report.html` in a browser. HTML reports may not preview inside Teams.
3. Share large files such as a demo video through OneDrive or a video platform link instead of attaching them.

### Longer term: a Git repository

A private Git repository gives version history and makes prompt versions easy to track. Add a `.gitignore` so cloned repositories are not committed:

```
runs/*/repo/
__pycache__/
.DS_Store
```
