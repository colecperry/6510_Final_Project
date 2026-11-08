# Phase 3: technical credit

Identify the most significant technical credit in this repository.

Also read the Phase 2 debt results: {debt_path}
Reuse its decision IDs where a credit item comes from the same design decision, and add new decisions (continuing the numbering) for new ones.

Look for credit in these categories (use these exact category names):
- "abstraction": code that isolates the rest of the system from a library, platform or vendor
- "extension_point": designs that make adding a new variant cheap
- "automation": CI, smoke tests, formatting checks and other automated guards
- "modularity": clear boundaries that keep changes contained
- "documentation": docstrings, tutorials and recorded rationale
{domain_credit}

Apply this credit test to every candidate and record it in "credit_test":
(a) upfront_cost: was there extra cost up front, compared with the simplest alternative?
(b) makes_change_cheaper: does it make future change cheaper, as opposed to just giving users a feature?
(c) before_after: is there a before-and-after comparison, such as a similar change made before the investment existed? Describe it, or use null.
If (a) or (b) is false, it is not credit; leave it out or mark it over-engineering if it was built but never used.

For realised credit, measure the cash-in: find the later commits where a change was cheap because of the investment, and measure them with git show --stat or --numstat (for example, how many files changed when a new variant was added). "frequency" counts those cash-in commits in each window. "impact" summarises the measured benefit.

Use the same usage check for "realised" and for "over_engineering", so one item cannot land on both.

Then list credit-debt pairs: debt and credit items that share a decision_id. For each pair, say whether the decision is net credit, net debt or neutral, and explain why. Flag any evidence (the same file and commit) cited on both sides.

Return JSON in exactly this shape:

{
  "phase": "credit",
  "decisions": [
    {"decision_id": "DEC-07", "description": "one line", "introduced_commit": "abc12345 or null"}
  ],
  "items": [
    {
      "id": "C1",
      "kind": "credit",
      "decision_id": "DEC-07",
      "category": "abstraction",
      "title": "short title",
      "description": "two or three sentences",
      "evidence": [{"file": "path/to/file.py", "lines": "10-40 or null", "commit": "abc12345 or null", "note": "what this shows"}],
      "basis": "observed",
      "confidence_exists": "high",
      "confidence_impact": "high",
      "status": "realised",
      "frequency": {"all_history_commits": 9, "window_commits": 1, "method": "git command used"},
      "footprint": "large",
      "footprint_note": "why",
      "impact": "measured cash-in, for example: new backends needed 4 files each",
      "credit_test": {"upfront_cost": true, "makes_change_cheaper": true, "before_after": "description or null"}
    }
  ],
  "pairs": [
    {"pair_id": "P1", "decision_id": "DEC-01", "debt_ids": ["D1"], "credit_ids": ["C3"], "net": "debt", "explanation": "why", "shared_evidence": ["file@commit cited on both sides, or empty"]}
  ],
  "suspected_unconfirmed": ["things you suspected but could not confirm"],
  "self_check": [{"claim": "what was checked", "command": "command run", "result": "confirmed or corrected: details"}]
}

For credit, "status" must be "realised", "potential" or "over_engineering". Decisions only needs the decisions that are new in this phase.
