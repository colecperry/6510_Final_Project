# Phase 2: technical debt

Identify the most significant technical debt in this repository.

Look for debt in these categories (use these exact category names):
- "code": overly large or complex files and functions, duplication, commented-out code, dead code
- "design": tight coupling, unclear module boundaries, workarounds instead of proper fixes
- "test": missing or weak tests for important code
- "dependency": loose pinning, version-specific workarounds, packaging and build problems
- "documentation": missing design rationale, or docs that no longer match the code
{domain_debt}

Also look for implicit self-admitted debt: comments that describe a workaround, limitation or hack without using words such as TODO or FIXME. The Phase 1 keyword count undercounts these.

For each debt item, "impact" must describe the interest: what extra cost it creates, and on what kind of change. "frequency" must count the commits in each window that paid that interest, with the command used.

Return JSON in exactly this shape:

{
  "phase": "debt",
  "decisions": [
    {"decision_id": "DEC-01", "description": "one line", "introduced_commit": "abc12345 or null"}
  ],
  "items": [
    {
      "id": "D1",
      "kind": "debt",
      "decision_id": "DEC-01",
      "category": "code",
      "title": "short title",
      "description": "two or three sentences",
      "evidence": [{"file": "path/to/file.py", "lines": "10-40 or null", "commit": "abc12345 or null", "note": "what this shows"}],
      "basis": "observed",
      "confidence_exists": "high",
      "confidence_impact": "medium",
      "status": "realised",
      "frequency": {"all_history_commits": 12, "window_commits": 3, "method": "git command used"},
      "footprint": "medium",
      "footprint_note": "why",
      "impact": "the interest this debt charges"
    }
  ],
  "suspected_unconfirmed": ["things you suspected but could not confirm"],
  "self_check": [{"claim": "what was checked", "command": "command run", "result": "confirmed or corrected: details"}]
}

For debt, "status" must be "realised" or "potential".
