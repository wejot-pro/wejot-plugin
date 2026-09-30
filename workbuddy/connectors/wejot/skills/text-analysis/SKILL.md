---
name: text-analysis
description: Analyze authorized open-ended answers, reviews, feedback, or VOC through scenario-specific coding, bounded batch processing, traceable row-level evidence, deterministic acceptance and merge, and decision-oriented synthesis.
---

# Text Analysis

Use for qualitative or mixed-method analysis of open answers, reviews, feedback, opinions, sentiment, themes, needs, pain points, or customer voice. Treat data-quality cleaning as a separate concern even when both workflows are requested.

Infer the business setting from the request, file name, field names, and content. Ask for context only when it is genuinely unavailable and would change the coding frame.

- For consumer products, retail, FMCG, consumption experience, or brand VOC, read [references/consumer-voc.md](references/consumer-voc.md) and follow its six-step closed loop.
- For product feedback, support, SaaS, education, finance, hospitality, or another setting, read [references/general-text-analysis.md](references/general-text-analysis.md).

Optional validation, merge, and report-data scripts are bundled in this skill. Use them when their input contracts match the current batch artifacts; equivalent deterministic host-native processing is acceptable.

## Shared execution contract

1. Establish source, text field, language, population, time range, stable response identifier, permissions, and cleaning status. Fetch fresh WeJot data through `survey-data-fetch` or use a user-supplied authorized file.
2. Define and persist the coding frame and output schema before full processing. Keep data-quality labels separate from business-insight labels.
3. Profile volume before partitioning. Choose full processing, representative random sampling, stratified sampling, or user-confirmed filtering. A material coverage reduction requires explicit user confirmation and disclosure.
4. Partition the prepared data into bounded batches before semantic analysis. When the host supports independent workers, dispatch batches together; otherwise process the same partitions sequentially. Do not put raw source text in task descriptions when workers can read bounded batch artifacts.
5. Preserve one output row per stable source identifier. Validate every batch's schema, allowed values, unique identifiers, and input/output coverage. Retry only failed batches; after repeated failure, use a controlled fallback or report the gap.
6. Merge deterministically and recompute aggregates from merged rows. Review low-confidence cases, label conflicts, rare high-impact issues, and disagreements before synthesis.
7. Report coding definitions, processed and sampled populations, counts or proportions with denominators, representative permitted evidence, confidence or disagreement, emerging themes, limitations, and actionable next questions or decisions.

Do not have the coordinating agent serially improvise labels across a large raw dataset. Use a shared coding frame and independent bounded contexts so classification criteria remain stable. The exact worker arrangement is host-dependent; no proprietary agent type is required.

## Evidence and privacy

Every label and claim must be traceable to a source identifier and evidence. Preserve original text separately from derived labels. Redact unnecessary personal information before delegation or reporting. Quote only when permitted and necessary; otherwise use a faithful paraphrase linked to the source identifier.

Never invent excerpts, rows, counts, themes, sentiment, cultural meaning, commercial impact, or certainty. Do not silently reuse old data, mechanically classify semantic meaning from keyword matches alone, or merge malformed batch results.
