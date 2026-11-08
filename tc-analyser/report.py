#!/usr/bin/env python3
"""
Report step of the technical debt / technical credit PoC.

Reads the files in a run folder and writes one self-contained HTML report with charts.
No third-party packages, no internet needed: charts are inline SVG.

Usage:
    python report.py runs/yolov5            # writes runs/yolov5/report.html
    python report.py runs/yolov5 --open     # and opens it in the browser

Inputs (any missing phase is shown as "not run"):
    inventory.json, 02-debt.json, 03-credit.json, 04-verdict.json, run_log.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import webbrowser
from collections import Counter
from html import escape
from pathlib import Path

VERDICT_SCALE = ["clearly_in_debt", "leaning_debt", "balanced", "leaning_credit", "clearly_in_credit"]


def e(x) -> str:
    return escape("" if x is None else str(x))


def load(run: Path, name: str):
    p = run / name
    return json.loads(p.read_text()) if p.exists() else None


def label(s: str | None) -> str:
    return (s or "—").replace("_", " ")


# ---------------------------------------------------------------- charts (inline SVG)

def hbar(rows, unit="", label_w=200, w=680):
    """rows: list of (label, value, css_class). Values may be None."""
    rows = [r for r in rows if r[1] is not None]
    if not rows:
        return "<p class='muted'>No data.</p>"
    vmax = max(r[1] for r in rows) or 1
    bh, gap = 24, 10
    h = len(rows) * (bh + gap) + 6
    bar_max = w - label_w - 120
    out = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">']
    for i, (lab, val, cls) in enumerate(rows):
        y = i * (bh + gap) + 3
        bw = max(2, bar_max * val / vmax)
        short = lab if len(lab) <= 30 else lab[:28] + "…"
        out.append(f'<text x="{label_w - 10}" y="{y + 17}" text-anchor="end" class="lab"><title>{e(lab)}</title>{e(short)}</text>')
        out.append(f'<rect x="{label_w}" y="{y}" width="{bw:.1f}" height="{bh}" rx="3" class="{cls}"/>')
        out.append(f'<text x="{label_w + bw + 8:.1f}" y="{y + 17}" class="val">{val:,}{e(unit)}</text>')
    out.append("</svg>")
    return "\n".join(out)


def paired_bars(rows, label_w=200, w=680):
    """rows: list of (label, a, b) drawn as two thin bars: a = all history, b = window."""
    rows = [r for r in rows if r[1] is not None or r[2] is not None]
    if not rows:
        return "<p class='muted'>No data.</p>"
    vmax = max(max(r[1] or 0, r[2] or 0) for r in rows) or 1
    bh, gap = 11, 12
    h = len(rows) * (2 * bh + gap) + 40
    bar_max = w - label_w - 70
    out = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">']
    for i, (lab, a, b) in enumerate(rows):
        y = i * (2 * bh + gap) + 4
        short = lab if len(lab) <= 30 else lab[:28] + "…"
        out.append(f'<text x="{label_w - 10}" y="{y + 16}" text-anchor="end" class="lab"><title>{e(lab)}</title>{e(short)}</text>')
        for j, (v, cls) in enumerate(((a, "neutral"), (b, "accent"))):
            if v is None:
                continue
            bw = max(2, bar_max * v / vmax)
            yy = y + j * bh
            out.append(f'<rect x="{label_w}" y="{yy}" width="{bw:.1f}" height="{bh - 1}" rx="2" class="{cls}"/>')
            out.append(f'<text x="{label_w + bw + 6:.1f}" y="{yy + 9}" class="val small">{v:,}</text>')
    ly = h - 14
    out.append(f'<rect x="{label_w}" y="{ly - 9}" width="11" height="11" rx="2" class="neutral"/>'
               f'<text x="{label_w + 16}" y="{ly}" class="lab">All history</text>'
               f'<rect x="{label_w + 110}" y="{ly - 9}" width="11" height="11" rx="2" class="accent"/>'
               f'<text x="{label_w + 126}" y="{ly}" class="lab">Window</text>')
    out.append("</svg>")
    return "\n".join(out)


def stacked(segs, w=680):
    """segs: list of (label, value, css_class)."""
    total = sum(v for _, v, _ in segs)
    if not total:
        return "<p class='muted'>No data.</p>"
    out = [f'<svg viewBox="0 0 {w} 92" class="chart" role="img">']
    x = 0.0
    for lab, v, cls in segs:
        sw = w * v / total
        if sw > 0:
            out.append(f'<rect x="{x:.1f}" y="6" width="{sw:.1f}" height="32" class="{cls}"><title>{e(lab)}: {v}</title></rect>')
            if sw > 34:
                dark = cls in ("debt-real", "cred-real", "neutral", "accent")
                out.append(f'<text x="{x + sw / 2:.1f}" y="27" text-anchor="middle" class="{"inbar" if dark else "inbar-dark"}">{v}</text>')
        x += sw
    lx = 0
    for lab, v, cls in segs:
        t = f"{label(lab)} ({v})"
        out.append(f'<rect x="{lx}" y="58" width="11" height="11" rx="2" class="{cls}"/><text x="{lx + 16}" y="68" class="lab">{e(t)}</text>')
        lx += 16 + len(t) * 7.2 + 20
    out.append("</svg>")
    return "\n".join(out)


def verdict_scale(window: str | None, history: str | None, w=680):
    x0, x1 = 75, 605
    step = (x1 - x0) / 4
    out = [f'<svg viewBox="0 0 {w} 140" class="chart" role="img">',
           f'<rect x="{x0}" y="90" width="{x1 - x0}" height="8" rx="4" class="neutral" opacity="0.35"/>']
    for i, v in enumerate(VERDICT_SCALE):
        x = x0 + i * step
        out.append(f'<circle cx="{x}" cy="94" r="6" class="neutral"/>')
        out.append(f'<text x="{x}" y="125" text-anchor="middle" class="lab">{e(label(v).capitalize())}</text>')
    marks = [(window, "Last 24 months", "debt-real", -1), (history, "All history", "cred-real", 1)]
    same = window == history
    for val, name, cls, side in marks:
        if val not in VERDICT_SCALE:
            continue
        x = x0 + VERDICT_SCALE.index(val) * step + (side * 14 if same else 0)
        out.append(f'<path d="M{x} 80 L{x - 9} 62 L{x + 9} 62 Z" class="{cls}"/>')
        ty = 34 if side < 0 or not same else 50
        out.append(f'<text x="{x}" y="{ty}" text-anchor="middle" class="head">{e(name)}</text>')
    out.append("</svg>")
    return "\n".join(out)


def ledger(debt_items, credit_items, w=680):
    col, rh, gap = 330, 28, 7

    def block(items, x, y0, cls, s):
        for i, it in enumerate(items):
            y = y0 + i * (rh + gap)
            title = it.get("title", "")
            short = title if len(title) <= 40 else title[:38] + "…"
            s.append(f'<rect x="{x}" y="{y}" width="{col}" height="{rh}" rx="4" class="{cls}"><title>{e(title)}</title></rect>')
            s.append(f'<text x="{x + 10}" y="{y + 19}" class="blk-k {cls}-t">{e(it.get("id"))}</text>')
            s.append(f'<text x="{x + 52}" y="{y + 19}" class="blk-t {cls}-t">{e(short)}</text>')
        return y0 + len(items) * (rh + gap)

    def group(items, status):
        return [i for i in items if i.get("status") == status]

    s = []
    y = 20
    s.append(f'<text x="0" y="{y}" class="head">Debt</text><text x="{w - col}" y="{y}" class="head">Credit</text>')
    yl = yr = 34
    for status, cls, title in (("realised", "debt-real", "Realised"), ("potential", "debt-pot", "Potential")):
        items = group(debt_items, status)
        if items:
            s.append(f'<text x="0" y="{yl + 14}" class="sub">{title}</text>')
            yl = block(items, 0, yl + 22, cls, s) + 6
    for status, cls, title in (("realised", "cred-real", "Realised"), ("potential", "cred-pot", "Potential"),
                               ("over_engineering", "over", "Possible over-engineering")):
        items = group(credit_items, status)
        if items:
            s.append(f'<text x="{w - col}" y="{yr + 14}" class="sub">{title}</text>')
            yr = block(items, w - col, yr + 22, cls, s) + 6
    h = max(yl, yr) + 6
    return f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">' + "".join(s) + "</svg>"


# ---------------------------------------------------------------- sections

def item_table(items, kind):
    if not items:
        return "<p class='muted'>Not run.</p>"
    rows = []
    for it in items:
        f = it.get("frequency") or {}
        ev = "".join(
            f"<li><code>{e(x.get('file'))}{(':' + e(x.get('lines'))) if x.get('lines') else ''}</code>"
            f"{(' · <code>' + e(str(x.get('commit'))[:8]) + '</code>') if x.get('commit') else ''}"
            f"{(' — ' + e(x.get('note'))) if x.get('note') else ''}</li>"
            for x in it.get("evidence") or [])
        extra = ""
        if kind == "credit" and it.get("credit_test"):
            ct = it["credit_test"]
            extra = (f"<p><strong>Credit test.</strong> Extra cost up front: {e(ct.get('upfront_cost'))}. "
                     f"Makes change cheaper: {e(ct.get('makes_change_cheaper'))}. "
                     f"Before and after: {e(ct.get('before_after') or 'none recorded')}.</p>")
        status_cls = {"realised": "real", "potential": "pot", "over_engineering": "over"}.get(it.get("status"), "pot")
        tag_cls = f"tag {kind}-{status_cls}"
        rows.append(f"""
<tr>
  <td><strong>{e(it.get('id'))}</strong></td>
  <td><details><summary>{e(it.get('title'))}</summary>
    <div class="detail">
      <p>{e(it.get('description'))}</p>
      <p><strong>{'Interest' if kind == 'debt' else 'Cash-in'}.</strong> {e(it.get('impact'))}</p>
      {extra}
      <p><strong>Footprint.</strong> {e(it.get('footprint'))}: {e(it.get('footprint_note'))}</p>
      <p><strong>Frequency method.</strong> <code>{e(f.get('method'))}</code></p>
      <p><strong>Evidence.</strong></p><ul>{ev}</ul>
      <p class="muted">Decision {e(it.get('decision_id'))} · {e(it.get('basis'))} · confidence exists {e(it.get('confidence_exists'))}, impact {e(it.get('confidence_impact'))}</p>
    </div></details></td>
  <td>{e(label(it.get('category')))}</td>
  <td><span class="{tag_cls}">{e(label(it.get('status')))}</span></td>
  <td class="num">{e(f.get('window_commits') if f.get('window_commits') is not None else '—')}</td>
  <td class="num">{e(f.get('all_history_commits') if f.get('all_history_commits') is not None else '—')}</td>
  <td>{e(it.get('footprint'))}</td>
</tr>""")
    return f"""<div class="scroll"><table>
<thead><tr><th>ID</th><th>Finding (click for details)</th><th>Category</th><th>Status</th><th class="num">Window commits</th><th class="num">All commits</th><th>Footprint</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>"""


def list_block(items, fmt):
    if not items:
        return "<p class='muted'>None recorded.</p>"
    return "<ul>" + "".join(f"<li>{fmt(x)}</li>" for x in items) + "</ul>"


def run_table(log):
    if not log or not log.get("runs"):
        return "<p class='muted'>No run log.</p>"
    phases = {}
    meta = {}
    for run in log["runs"]:  # later runs overwrite earlier ones for the same phase
        for p in run.get("phases", []):
            phases[p["phase"]] = p
            meta[p["phase"]] = run
    rows, tot_s, tot_c, tot_t = [], 0, 0, 0
    for name in ("debt", "credit", "verdict"):
        p = phases.get(name)
        if not p:
            rows.append(f"<tr><td>{name}</td><td colspan='6' class='muted'>not run</td></tr>")
            continue
        s, c, t = p.get("elapsed_seconds") or 0, p.get("total_cost_usd") or 0, p.get("num_turns") or 0
        tot_s, tot_c, tot_t = tot_s + s, tot_c + c, tot_t + t
        ok = "yes" if p.get("repo_unchanged", True) else "<strong>no</strong>"
        probs = len(p.get("validation_problems") or [])
        rows.append(f"<tr><td>{name}</td><td class='num'>{s / 60:.1f}</td><td class='num'>{t}</td>"
                    f"<td class='num'>${c:.2f}</td><td>{ok}</td><td class='num'>{probs}</td>"
                    f"<td>{e(meta[name].get('claude_version'))}</td></tr>")
    rows.append(f"<tr class='total'><td>Total</td><td class='num'>{tot_s / 60:.1f}</td><td class='num'>{tot_t}</td>"
                f"<td class='num'>${tot_c:.2f}</td><td></td><td></td><td></td></tr>")
    return ("<div class='scroll'><table><thead><tr><th>Phase</th><th class='num'>Minutes</th><th class='num'>Turns</th>"
            "<th class='num'>Cost estimate</th><th>Repo unchanged</th><th class='num'>Validation problems</th>"
            "<th>Claude Code</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")


# ---------------------------------------------------------------- page

def build(run: Path) -> str:
    inv = load(run, "inventory.json")
    if not inv:
        raise SystemExit(f"{run / 'inventory.json'} not found. Run metrics.py first.")
    debt = load(run, "02-debt.json") or {}
    credit = load(run, "03-credit.json") or {}
    verdict = load(run, "04-verdict.json") or {}
    log = load(run, "run_log.json")
    m = inv["meta"]
    d_items, c_items = debt.get("items", []), credit.get("items", [])
    all_items = d_items + c_items

    # charts
    cats = sorted({i.get("category") for i in all_items if i.get("category")})
    d_cat, c_cat = Counter(i.get("category") for i in d_items), Counter(i.get("category") for i in c_items)
    cat_rows = []
    for c in cats:
        if d_cat[c]:
            cat_rows.append((f"{label(c)} (debt)", d_cat[c], "debt-real"))
        if c_cat[c]:
            cat_rows.append((f"{label(c)} (credit)", c_cat[c], "cred-real"))
    freq_rows = [(f"{i['id']} {i.get('title', '')}", (i.get("frequency") or {}).get("all_history_commits"),
                  (i.get("frequency") or {}).get("window_commits")) for i in all_items]
    status_segs = [(s, n, cls) for s, n, cls in (
        ("debt realised", sum(i.get("status") == "realised" for i in d_items), "debt-real"),
        ("debt potential", sum(i.get("status") == "potential" for i in d_items), "debt-pot"),
        ("credit realised", sum(i.get("status") == "realised" for i in c_items), "cred-real"),
        ("credit potential", sum(i.get("status") == "potential" for i in c_items), "cred-pot"),
        ("over-engineering", sum(i.get("status") == "over_engineering" for i in c_items), "over")) if n]

    size, churn, tests, deps, satd, ci = inv["size"], inv["churn"], inv["tests"], inv["dependencies"], inv["satd"], inv["ci"]
    largest = hbar([(r["file"], r["lines"], "neutral") for r in size["largest_files"][:10]], " lines")
    win = {r["file"]: r["commits"] for r in churn["window"]["top_files"]}
    churn_rows = [(r["file"] + ("" if r["still_exists"] else " (gone)"), r["commits"], win.get(r["file"]))
                  for r in churn["all"]["top_files"][:10]]
    dep_cls = {"exact": "cred-real", "bounded": "cred-pot", "minimum_only": "debt-pot", "open": "debt-real",
               "property": "neutral", "managed_or_inherited": "neutral", "range": "debt-pot", "snapshot": "debt-real",
               "dynamic": "debt-real", "other": "neutral"}
    deps_chart = stacked([(k, v, dep_cls.get(k, "neutral")) for k, v in sorted(deps.get("by_class", {}).items(), key=lambda kv: -kv[1])])
    doc = inv["docs"].get("docstrings") or {}
    doc_chart = hbar([(k.capitalize(), round(v["share"] * 100, 1), "cred-real") for k, v in doc.items() if v.get("share") is not None], "%", 130) if doc else ""
    tests_chart = hbar([("Non-test source files", tests.get("non_test_source_files"), "neutral"),
                        ("Test files", tests.get("test_files"), "debt-pot"),
                        ("Test functions", tests.get("test_functions"), "accent")], "", 190)

    pairs = credit.get("pairs", [])
    pair_rows = "".join(
        f"<tr><td>{e(p.get('pair_id'))}</td><td>{e(p.get('decision_id'))}</td><td>{e(', '.join(p.get('debt_ids', [])))}</td>"
        f"<td>{e(', '.join(p.get('credit_ids', [])))}</td><td><span class='tag net-{e(p.get('net'))}'>{e(p.get('net'))}</span></td>"
        f"<td>{e(p.get('explanation'))}</td></tr>" for p in pairs)
    sa = verdict.get("self_assessment", {})

    verdict_html = "<p class='muted'>The verdict phase has not been run.</p>"
    if verdict:
        verdict_html = f"""
<p class="lede">Next change (last 24 months): <strong>{e(label(verdict.get('verdict_window')))}</strong>.
Whole life: <strong>{e(label(verdict.get('verdict_all_history')))}</strong>.</p>
<figure>{verdict_scale(verdict.get('verdict_window'), verdict.get('verdict_all_history'))}
<figcaption>Verdict on a five-point scale for each time window. The window runs from {e(m['window']['since'])} to {e(m['window']['until'])}.</figcaption></figure>
<h3>Items that drove the verdict</h3>
{list_block(verdict.get('key_items'), lambda k: f"<strong>{e(k.get('id'))}</strong>: {e(k.get('why'))} <span class='muted'>If wrong: {e(label(k.get('verdict_if_wrong')))}.</span>")}
<h3>How the items were weighed</h3><p>{e(verdict.get('weighing_method'))}</p>
<p><strong>Pairs.</strong> {e(verdict.get('pairs_handling'))}</p>"""

    css = CSS
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Debt and credit report: {e(m['source'])}</title>
<style>{css}</style></head>
<body><main>
<h1>Technical debt and credit report</h1>
<p class="meta"><strong>{e(m['source'])}</strong><br>
Commit <code>{e(m['head_short'])}</code> ({e(m['head_date'])}) on <code>{e(m['branch'])}</code> ·
language {e(inv['language']['primary'])} · {inv['history']['commits']['all']:,} commits since {e(inv['history']['first_commit_date'])} ·
window {e(m['window']['since'])} to {e(m['window']['until'])} · report generated {dt.date.today().isoformat()}</p>

<h2>Verdict</h2>
{verdict_html}

<h2>Ledger</h2>
<figure>{ledger(d_items, c_items) if all_items else "<p class='muted'>No findings yet.</p>"}
<figcaption>Each block is one finding. Darker means the cost or benefit is visible in the history; lighter means it is still a risk or an unproven investment. Hover a block for its full title.</figcaption></figure>
<figure>{stacked(status_segs) if status_segs else ''}<figcaption>Findings by status.</figcaption></figure>

<h2>Technical debt</h2>
{item_table(d_items, 'debt')}

<h2>Technical credit</h2>
{item_table(c_items, 'credit')}

<h2>Credit-debt pairs</h2>
<p>Pairs are debt and credit items that come from the same design decision. The verdict counts each pair once, at its net value.</p>
{('<div class="scroll"><table><thead><tr><th>Pair</th><th>Decision</th><th>Debt</th><th>Credit</th><th>Net</th><th>Why</th></tr></thead><tbody>' + pair_rows + '</tbody></table></div>') if pairs else "<p class='muted'>No pairs recorded.</p>"}

<h2>Findings in charts</h2>
<h3>Findings by category</h3>
<figure>{hbar(cat_rows, '', 230) if cat_rows else "<p class='muted'>No findings.</p>"}</figure>
<h3>How often each finding recurs</h3>
<figure>{paired_bars(freq_rows, 260)}
<figcaption>Commits counted by Claude as paying interest (debt) or cashing in (credit), over all history and within the window. Architectural credit often shows zero in the window because it was cashed in earlier.</figcaption></figure>

<h2>Measured facts (Phase 1, no AI)</h2>
<h3>Largest files</h3><figure>{largest}</figure>
<h3>Most-changed files</h3><figure>{paired_bars(churn_rows, 230)}
<figcaption>Raw churn per file path. Renames are not followed, so a renamed file's history is split.</figcaption></figure>
<h3>Tests</h3><figure>{tests_chart}<figcaption>{e(tests.get('method'))}. CI workflows that run tests: {ci['workflows_running_tests']} of {len(ci['github_workflows'])}.</figcaption></figure>
<h3>Dependencies</h3><figure>{deps_chart}<figcaption>{deps['specs']} dependency specifications. Lock files: {e(', '.join(deps.get('lock_files') or []) or 'none')}.</figcaption></figure>
{('<h3>Docstrings</h3><figure>' + doc_chart + '</figure>') if doc_chart else ''}
<p>Debt-marker comments found by keyword: <strong>{satd['total']}</strong> {e(satd['by_keyword'])}. Keyword search undercounts; Phase 2 looks for workarounds described in other words.</p>

<h2>Self-assessment</h2>
<h3>Contradictions between phases</h3>
{list_block(sa.get('contradictions'), lambda c: f"{'Resolved' if c.get('resolved') else '<strong>Unresolved</strong>'}: {e(c.get('description'))}" + (f" <span class='muted'>{e(c.get('resolution'))}</span>" if c.get('resolution') else ''))}
<h3>Least confident findings</h3>
{list_block(sa.get('least_confident'), lambda x: f"<strong>{e(x.get('id'))}</strong>: {e(x.get('reason'))}")}
<h3>What the code and history can't settle</h3>
{list_block(sa.get('undeterminable'), lambda x: f"{e(x.get('question'))} <span class='muted'>Needs: {e(x.get('data_needed'))}</span>")}
<h3>Suggested changes to the method</h3>
{list_block(verdict.get('method_feedback'), e)}
<h3>Suspected but not confirmed</h3>
{list_block((debt.get('suspected_unconfirmed') or []) + (credit.get('suspected_unconfirmed') or []), e)}

<h2>How this report was produced</h2>
<p>Phase 1 was measured by a script with no AI. Phases 2 to 4 were run by Claude Code in headless mode, each as a separate session with read-only tools, returning JSON that was validated before saving.
Self-checks recorded: debt {len(debt.get('self_check', []))}, credit {len(credit.get('self_check', []))}, verdict {len(verdict.get('self_check', []))}.</p>
{run_table(log)}
<p class="muted">Cost figures are Claude Code's own estimates and may differ from actual billing. Prompts and full responses are in the <code>raw/</code> folder next to this report.</p>
</main></body></html>"""


CSS = """
:root{--paper:#FAFBFC;--ink:#1C2733;--muted:#5B6878;--rule:#D9DFE6;--panel:#F0F3F6;--code:#EEF1F4;
--debt:#A3431F;--debt-soft:#E9C3B2;--credit:#1E6E62;--credit-soft:#B9DDD5;--neutral:#7D8B9B;--accent:#3A6EA5;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--paper:#141A21;--ink:#E4E9EF;--muted:#9AA7B6;--rule:#2C3743;--panel:#1B232C;--code:#1F2832;
--debt:#E08560;--debt-soft:#5A3020;--credit:#5FC2B0;--credit-soft:#1E4A43;--neutral:#7D8B9B;--accent:#7FA7D6;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:58rem;margin:0 auto;padding:2.5rem 1.2rem 4rem}
h1{font-size:2rem;line-height:1.2;margin:0 0 .6rem}
h2{font-size:1.35rem;margin:2.8rem 0 .7rem;padding-top:1rem;border-top:1px solid var(--rule)}
h3{font-size:1.05rem;margin:1.6rem 0 .4rem}
p,li{max-width:72ch}
.meta{color:var(--muted);font-size:.92rem}.muted{color:var(--muted)}.lede{font-size:1.1rem}
code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.85em;background:var(--code);padding:.08em .32em;border-radius:3px}
figure{margin:1.2rem 0 1.8rem}figcaption{font-size:.85rem;color:var(--muted);margin-top:.4rem}
.scroll{overflow-x:auto}
.chart{width:100%;height:auto;display:block;min-width:520px}
.chart .lab{fill:var(--ink);font-size:12.5px}.chart .val{fill:var(--muted);font-size:12.5px}.chart .small{font-size:10.5px}
.chart .inbar{fill:#fff;font-size:12.5px;font-weight:600}.chart .inbar-dark{fill:var(--ink);font-size:12.5px;font-weight:600}.chart .head{fill:var(--ink);font-size:15px;font-weight:600}
.chart .sub{fill:var(--muted);font-size:12px}.chart .blk-k{font-size:12px;font-weight:600}.chart .blk-t{font-size:12.5px}
.neutral{fill:var(--neutral)}.accent{fill:var(--accent)}
.debt-real{fill:var(--debt)}.debt-pot{fill:var(--debt-soft)}.cred-real{fill:var(--credit)}.cred-pot{fill:var(--credit-soft)}
.over{fill:var(--panel);stroke:var(--neutral);stroke-dasharray:4 3}
.debt-real-t,.cred-real-t{fill:#fff}.debt-pot-t,.cred-pot-t,.over-t{fill:var(--ink)}
table{border-collapse:collapse;width:100%;font-size:.9rem;min-width:640px}
th,td{text-align:left;vertical-align:top;padding:.5rem .55rem;border-bottom:1px solid var(--rule)}
th{color:var(--muted);font-weight:600;font-size:.8rem}.num{text-align:right;white-space:nowrap}
tr.total td{font-weight:600}
details summary{cursor:pointer}.detail{padding:.4rem 0 .2rem;font-size:.88rem}.detail p{margin:.35rem 0}.detail ul{margin:.2rem 0 .4rem 1rem;padding:0}
.tag{display:inline-block;font-size:.75rem;font-weight:600;padding:.05rem .45rem;border-radius:3px;white-space:nowrap}
.debt-real{}.tag.debt-real{background:var(--debt);color:#fff}.tag.debt-pot{background:var(--debt-soft);color:var(--ink)}
.tag.credit-real{background:var(--credit);color:#fff}.tag.credit-pot{background:var(--credit-soft);color:var(--ink)}
.tag.credit-over{background:var(--panel);color:var(--ink);border:1px dashed var(--neutral)}
.tag.net-credit{background:var(--credit);color:#fff}.tag.net-debt{background:var(--debt);color:#fff}.tag.net-neutral{background:var(--panel);color:var(--ink);border:1px solid var(--rule)}
"""


def main():
    p = argparse.ArgumentParser(description="Build the HTML report for a run folder.")
    p.add_argument("run_dir", type=Path)
    p.add_argument("--open", action="store_true", help="open the report in the browser")
    args = p.parse_args()
    out = args.run_dir / "report.html"
    out.write_text(build(args.run_dir), encoding="utf-8")
    print(f"Wrote {out}")
    if args.open:
        webbrowser.open(out.resolve().as_uri())


if __name__ == "__main__":
    main()
