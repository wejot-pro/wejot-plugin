---
name: data-analysis
description: Analyze authorized survey or tabular data through a gated four-phase workflow with a durable plan, reproducible calculations, structured result artifacts, acceptance checks, and evidence-backed reporting.
---

# Data Analysis

Use this skill for statistics, comparisons, charts, insights, dashboards, scoring, or reports based on survey responses or uploaded tabular data.

- For WeJot responses, use `survey-data-fetch` first unless the user supplied an authorized current export.
- For data-quality review, exclusions, invalid responses, deduplication, or cleaning, use `data-cleaning` before treating the analysis population as final.
- For systematic coding of open text, use `text-analysis`.
- Survey authoring collects answers; post-hoc weighting, scoring, risk grading, and analytical reports belong here rather than in questionnaire JavaScript unless respondents must see an immediate in-form result.

Follow the four phases in order. Do not calculate or present findings before the applicable ingest and planning gates are complete.

## 1. Ingest and profile

Preserve the original source. Establish its provenance, version or snapshot, population, row and column counts, stable identifiers, types, missingness, weights, filters, timing, and available metadata.

For structured attachments, create one normalized tabular working copy and a compact machine-readable profile. Reuse that profile for planning instead of repeatedly reading or printing the complete source merely to rediscover its shape. Keep original column names stable unless a documented mapping is required.

The profile must identify at least:

- source and normalized-data references;
- rows, columns, names, and inferred types;
- missingness and representative value distributions;
- candidate key fields, weights, filters, and identifiers;
- fields relevant to the user's objectives;
- structural, freshness, or metadata limitations.

Maintain a durable artifact index or manifest that records each generated artifact, its phase, and a short summary. Do not leave the only record of source shape or later findings in transient console output.

Stop if the data is empty, stale for the requested decision, structurally incompatible, unauthorized, or insufficient for the requested inference. Never fabricate replacement rows or silently substitute an older dataset.

## 2. Plan — hard gate

Read the profile and any user-supplied framework, scoring rubric, metric definition, or report structure. Treat an explicit framework as authoritative; report unsupported fields and resolve conflicts instead of silently dropping criteria.

If the user already supplied objectives, dimensions, or questions, treat them as the analysis framework. Ask for clarification only when an unresolved choice would materially change metrics, population, weighting, date windows, missing-value treatment, multiple-response denominators, or interpretation.

Write a durable machine-readable analysis plan before computation. For every topic specify:

- stable topic identifier and intended result artifact;
- research objective and analysis question;
- source population, inclusion/exclusion rules, and filters;
- numerator, denominator, weight, statistic, comparison, and uncertainty treatment;
- required source fields and unsupported assumptions;
- acceptance checks and intended presentation.

Read the written plan back and verify that its topic count, outputs, and objectives agree. Computation is blocked until this read-back succeeds.

Estimate scale at this point. A small coherent plan may run in one or two deterministic batches. When there are many topics, multiple data sources or groups, repeated analyses, or more work than one context can reliably verify, partition the plan and use independent workers in parallel when the host supports them. Otherwise process the same bounded partitions sequentially. Do not prescribe a proprietary worker type.

## 3. Compute

Use the normalized data and the confirmed plan as the only computation scope.

- Batch related calculations; do not issue one tiny operation per number.
- Map every planned topic to one structured result artifact.
- Include source references, filters, valid sample size, denominator, formula or method, result, uncertainty where appropriate, and limitations.
- Preserve stable source identifiers and deterministic arithmetic.
- Update the artifact index after successful writes.
- Never put raw source rows into a worker prompt when a bounded data reference or partition can be used instead.

For partitioned work, validate every partition's output schema, source coverage, and identifiers before merging. Retry only the failed partition; after repeated failure, fall back to a smaller deterministic computation or report the unsupported topic. Do not silently omit it.

Before narration, verify totals, subgroup reconciliation, weighted versus unweighted distinctions, missing-value handling, duplicate identifiers, impossible values, scale direction, and denominator consistency. Recalculate aggregates from structured outputs rather than adding prose estimates.

## 4. Present

Read the artifact index and structured result artifacts; do not rely on remembered console output or prior-chat numbers.

State findings, caveats, and decision implications directly. Choose prose, tables, charts, or a report according to the relationship being explained and what the host can reliably render. Use the smallest visualization that materially improves understanding.

Every narrative number must be traceable to a result artifact or source field. State denominators for percentages and disclose sampling, filtering, exclusions, weighting, and missingness. Distinguish:

- descriptive association from causal claims;
- statistical significance from practical importance;
- weighted from unweighted estimates;
- valid responses from excluded or missing responses;
- respondent-based from selection-based percentages for multi-select items.

For scales or indices, document item mapping, reverse coding, missing-item policy, reliability checks, and scoring formula. For group comparisons, use a consistent population and denominator and report effect size or absolute difference plus uncertainty when supportable.

## Completion criteria

The analysis is complete only when:

- provenance and the analyzed snapshot are identified;
- ingest/profile and plan gates have passed;
- every planned topic is either backed by a validated result artifact or explicitly reported as unsupported;
- the artifact index is current;
- final numbers reconcile with the structured results;
- limitations and unsupported objectives are visible.

Never fabricate data, hide uncertainty behind polished visuals, overstate precision, infer causation from association, or present a transient calculation as an auditable result.
