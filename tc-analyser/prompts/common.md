You are analysing a software repository for technical debt (TD) and technical credit (TC) as part of a research study. Your output is parsed by a program, so follow the output rules exactly.

## Definitions

- Technical debt: a shortcut or sub-optimal choice that creates future cost or friction when the system needs to change. The recurring extra cost is the "interest".
- Technical credit (Gorton, Bucaioni and Pelliccione, CACM): the benefit created by a strategic design decision that cost more up front but makes future change cheaper. Credit is realised only once it has actually been used. An investment with no observed use may be over-engineering.
- Debt is "realised" when the history shows interest already paid (repeated manual fixes, bugs, divergence). It is "potential" when it is a risk that has not yet caused cost.

## Rules

1. Do not modify, create or delete any file. You only need to read files and run read-only git commands.
2. All line numbers refer to the current HEAD commit, {head_short}.
3. Use two fixed time windows for every frequency you report: all history, and the window {window_since} to {window_until}. Report frequencies as commit counts and state the git command used. Never write vague phrases such as "often" or "roughly quarterly" in place of a count.
4. Mark every item as "observed" (seen directly in code, config or history) or "inferred" (your interpretation).
5. Give confidence separately for whether the item exists (confidence_exists) and for how much it matters (confidence_impact), each as "low", "medium" or "high".
6. Group items by design decision. Each decision gets an ID such as "DEC-01". Tag every debt and credit item with the decision_id it comes from, so that credit-debt pairs can be found from shared IDs.
7. Footprint is "small" (one file or a small part of one area), "medium" (one module or several files) or "large" (several modules, or code touched by a large share of recent commits). Explain it in footprint_note.
8. Prefer depth over breadth: report the 10 to 15 most significant items.
9. Before you answer, run a self-check: re-derive every number you quote, and back every "none", "never" or "all" claim with a command. Record the checks in self_check. If a check fails, fix the item before answering.

## Output rules

Return a single JSON object and nothing else: no prose before or after it, and no Markdown code fences. Use null for any value you could not determine, and explain why in a note.

## Context

Repository: {repo_name}
Primary language: {language}
Measured facts from Phase 1 (deterministic script, no AI): {inventory_path}
Read that file first and use it as your starting evidence.
