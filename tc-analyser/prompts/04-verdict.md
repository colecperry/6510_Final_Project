# Phase 4: verdict and self-assessment

Read the earlier phase results:
- Phase 2 debt: {debt_path}
- Phase 3 credit: {credit_path}

Base this phase on those files and the Phase 1 facts. Only check the code or git history to resolve a contradiction between them.

Part 1, verdict. Give two verdicts, one for each time window, each as one of: "clearly_in_debt", "leaning_debt", "balanced", "leaning_credit", "clearly_in_credit".
- verdict_window: what the next change to this repository is likely to cost, judged from the window {window_since} to {window_until}.
- verdict_all_history: the balance over the repository's whole life.
Do not just count items. Weigh each item by its status (realised or potential), its frequency in that window, its footprint and its confidence. Handle each credit-debt pair once, using its net value, so no decision is counted twice. Name the three items that most influenced the window verdict, and say what the verdict would become if each were wrong.

Part 2, self-assessment: which findings you are least confident in, which depend most on inference, what the code and history cannot settle and what data would, which findings another analyst would most likely report differently, and every contradiction between the phase files. For each contradiction, say whether you resolved it and how.

Part 3, method feedback: up to five changes to the phase prompts that would make the analysis more reliable or easier to compare across repositories.

Return JSON in exactly this shape:

{
  "phase": "verdict",
  "verdict_window": "leaning_debt",
  "verdict_all_history": "leaning_credit",
  "weighing_method": "how you weighed the items, in a few sentences",
  "pairs_handling": "how pairs were counted",
  "key_items": [{"id": "D1", "why": "why it mattered", "verdict_if_wrong": "balanced"}],
  "self_assessment": {
    "least_confident": [{"id": "C4", "reason": "why"}],
    "most_inferred": [{"id": "D9", "reason": "why"}],
    "undeterminable": [{"question": "what could not be settled", "data_needed": "what would settle it"}],
    "likely_to_differ": [{"id": "D3", "reason": "why"}],
    "contradictions": [{"description": "what disagrees", "resolved": true, "resolution": "what you found, with the command used, or null"}]
  },
  "method_feedback": ["suggestion"],
  "self_check": [{"claim": "what was checked", "command": "command run", "result": "confirmed or corrected: details"}]
}
