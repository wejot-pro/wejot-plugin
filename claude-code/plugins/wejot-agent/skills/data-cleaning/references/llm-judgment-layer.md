# Semantic judgment layer

Use semantic judgment only for checks that deterministic rules cannot decide reliably: open-text quality, business contradictions, and suspected duplicate content. Keep this layer separate from deterministic cleaning and return structured evidence; it never deletes rows directly.

## Partitioning

Prefer independent batches when the host can run them concurrently. If concurrency is unavailable, process the same batches sequentially without changing the contract.

- Open text: partition by question so each reviewer sees one question, its wording, and stable response identifiers. For a very large question, split again into bounded row batches.
- Business contradictions: use one batch per user-approved candidate question pair.
- Suspected duplicates: use one batch per deterministic duplicate group.

Keep each batch context narrow. Preserve stable response identifiers, redact unnecessary personal information in reviewer-visible output, and retain permitted source evidence in the audit artifact.

## Result contract

For open text, return response identifier, question identifier, verdict (valid, gibberish, copy, off-topic, or personal-data flag), confidence, evidence, and optional redacted text.

For a contradiction pair, return response identifier, pair identifier, contradiction boolean, confidence, and evidence.

For a duplicate group, return group identifier, member response identifiers, similarity assessment, duplicate boolean, proposed retained response, and evidence.

Ambiguous cases default to review, not exclusion. Small samples require a more conservative interpretation.

## Adversarial review

False exclusion of a valid response is the primary risk. Re-review low-confidence exclusion candidates from the opposite position: try to demonstrate that the response is valid unless the evidence is conclusive. Use two or three independent reviews when the host supports it, then require a majority before upgrading a borderline case from review to recommended exclusion.

Suggested confidence thresholds for re-review are 0.9 in conservative mode, 0.8 in standard mode, and 0.7 in aggressive mode. These are defaults, not universal facts; include the selected threshold in the user-confirmed rules.

## Merge

Merge semantic findings with deterministic flags into one review list containing response identifier, rule or dimension, evidence, confidence, adversarial-review result, and recommended action. The user decides the final disposition unless an explicitly confirmed automatic mode applies to conclusive deterministic rules.
