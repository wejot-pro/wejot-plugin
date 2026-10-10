---
name: data-cleaning
description: Profile and clean survey, feedback, or tabular data with reproducible deterministic checks, evidence-backed semantic review, a mandatory rule-confirmation gate, and auditable disposition.
---

# Data Cleaning

Use for missingness, duplicates, invalid values, speeders, straight-lining, routing violations, contradictory answers, low-quality open text, or pre-analysis quality review.

Preserve the raw source. Work on a copy, keep each rule configurable and explainable, and default to flagging rather than deleting. Deterministic checks belong in scripts; semantic ambiguity belongs in a separately audited judgment layer.

Read only the internal reference needed for the current stage:

- [references/cleaning-rules.md](references/cleaning-rules.md) for candidate rules and evidence.
- [references/rule-config-schema.md](references/rule-config-schema.md) before creating a reproducible deterministic-rule configuration.
- [references/llm-judgment-layer.md](references/llm-judgment-layer.md) before semantic review.

The included profile_data.py and apply_cleaning.py scripts are optional deterministic helpers. Use equivalent host-native data tooling when those scripts cannot run.

## Workflow

1. Ingest and profile
   - Confirm source, schema, respondent-visible identifier, population, and available metadata.
   - Profile types, missingness, ranges, duplicates, duration, routing fields, and open-text coverage.
   - State which checks are unavailable because required metadata is absent.
   - For WeJot exports, use serial as the respondent-visible answer identifier. Do not substitute an internal answer ID.

2. Propose and confirm rules — mandatory gate
   - Present a rule list covering applicable general, survey-specific, and business-logic checks.
   - For every rule include scope, signal, threshold, deterministic or semantic method, estimated impact when available, evidence, and proposed disposition.
   - Ask the user to confirm or revise the rules. Do not apply exclusions, invalidation, or value changes before explicit confirmation.

3. Apply approved deterministic rules
   - Use a reproducible configuration and operate on a copy.
   - Keep every triggered response, source value, rule, and action in an audit artifact.
   - Unless the user explicitly approved automatic handling for conclusive rules, mark rows for review instead of removing them.

4. Review semantic cases
   - Partition open-text questions, approved contradiction pairs, and suspected duplicate groups according to the internal judgment reference.
   - Keep stable identifiers, evidence, confidence, privacy treatment, and independent review of borderline exclusions.
   - Merge findings into a review list; do not let semantic reviewers mutate the dataset.

5. Obtain disposition
   - Show the user affected serials, evidence, and the proposed keep/exclude/change decision.
   - Apply only the decisions the user confirms.
   - Record confirmed exclusions in the cleaned output and audit artifact. Do not change the remote response status as part of this workflow.

6. Deliver
   - Return a cleaned copy, the confirmed rule configuration, and an audit log.
   - Report original and retained counts, exclusion rate, rule-level impact, constrained checks, material distribution changes, and remaining quality risks.

Never fabricate data, silently reuse stale data, physically delete the raw source, hide uncertain cases inside a threshold, or claim that a remote response status changed.
