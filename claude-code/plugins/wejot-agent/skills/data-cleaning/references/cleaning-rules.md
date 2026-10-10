# Survey Data Cleaning Rules

Use this catalog to propose applicable rules after profiling. Thresholds are defaults, not silent decisions; show them to the user and obtain confirmation before exclusion, invalidation, or value changes.

## Layers and dispositions

- Deterministic layer: missingness, ranges, formats, metadata duplicates, speed, straight-lining, skip violations, and hard profile contradictions.
- Semantic layer: open-text quality, project-specific contradictions, and content similarity. Review in bounded batches with evidence and stable identifiers.
- `hard_remove`: conclusive invalidity, still subject to the configured confirmation policy.
- `flag`: plausible concern requiring review.

Default to `flag`. Outliers and unusual people are not automatically invalid.

## General rules

### G1 Missingness

Detect missing required items, missing critical fields, or low overall completion. A standard default may flag records below 60% answer coverage. Decide separately whether missing values should remain missing, be imputed, or cause exclusion; this skill does not impute by default.

### G2 Invalid range or code

Check numeric bounds, allowed choice codes, and valid date ranges against the current questionnaire schema. Prefer fixing or excluding the invalid answer rather than invalidating the whole response unless the project rule requires it.

### G3 Duplicate submission

Combine signals. The same user identifier is strong evidence when repeat submissions are not allowed. IP alone and user agent alone are weak because shared networks and common devices are normal. IP, user agent, close timestamps, and highly similar content together form stronger evidence.

### G4 Format normalization

Normalize whitespace, case, width variants, units, and date formats only through reversible, audited transformations. Normalization is a data change, not an exclusion.

### G5 Numeric outlier

Flag values beyond a configured IQR or z-score threshold. A standard starting point is 1.5 IQR or absolute z-score above 3. Never auto-remove an outlier merely because it is rare.

## Survey-specific rules

### S1 Speeder

Use total or per-item duration only when reliable timing metadata exists. A standard candidate threshold is total duration below `item_count × median_seconds × 0.4`, or more than half of timed items below one second. Speed alone is normally a review flag; combine it with other evidence before exclusion.

### S2 Straight-lining

Measure repeated use of one column across matrix or aligned scale items. Account for reverse-coded items. One straight-lined matrix is usually a flag; several aligned blocks plus speeding can justify a stronger proposal.

### S3 Skip-logic violation

Compare answers with the versioned survey routing contract. Distinguish an answer that should have been skipped from a required visible question that is missing. Do not infer routing from labels alone.

### S4 Hard profile contradiction

Generate project-specific checks from actual profile questions, for example age versus birth year, work years versus age, incompatible region fields, or an answer to a biologically or contextually inapplicable item. Separate impossible contradictions from merely unusual combinations. Make every boundary configurable and preserve evidence.

### S5 Open-text quality

Review meaningless strings, pure punctuation, question repetition, irrelevant content, suspicious copying, and personal information. Redact unnecessary personal information before broad review. Keep permitted original evidence in the restricted audit record.

### S6 Upload validity

Check required presence, allowed extensions, file integrity, and configured size constraints. A missing required upload and an unusual but valid file are different dispositions.

## Project-specific contradictions

Derive candidate contradiction pairs from the actual questionnaire and research objective, then show them to the user. Examples include claiming never to use a product while rating its recent experience, or being screened out while still answering the main module. A candidate pair is not automatically a true contradiction; context, routing, and time windows matter.

## Duplicate hierarchy

| Signal | Typical strength |
|---|---|
| Same user identifier | strong when repeats are disallowed |
| Same IP | weak |
| Same user agent | very weak |
| Same IP + agent + close time | strong batch or automation signal |
| Metadata cluster + highly similar answers | strongest combined signal |

State which metadata is unavailable and downgrade the claim accordingly.

## Mode defaults

| Rule | Conservative | Standard | Aggressive |
|---|---:|---:|---:|
| Minimum answer rate | 50% | 60% | 70% |
| IQR outlier factor | 3.0 | 1.5 | 1.0 |
| Speeder duration factor | 0.3 | 0.4 | 0.5 |
| Straight-line threshold | 100% only | 95% | 90% |
| Content-similarity review threshold | 0.95 | 0.90 | 0.85 |

These are proposal defaults. The user's confirmed rules and project context take precedence.
