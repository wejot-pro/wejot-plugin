# General Text Analysis

Use this flow for open-ended feedback outside the specialized consumer-VOC loop.

## 1. Define the plan

Persist an analysis plan containing:

- source and stable identifier;
- text and context fields;
- population, language, time range, filters, and sampling decision;
- requested outputs such as sentiment, theme, subtheme, need, pain point, severity, intent, feature, journey stage, and evidence;
- allowed labels, definitions, unknown/other handling, confidence scale, and output schema.

Run a small representative pilot before full processing. Revise overlapping, ambiguous, or unusable labels and then freeze the shared frame for all batches.

## 2. Prepare and size the data

Normalize only the fields required for analysis while retaining stable identifiers and an untouched original source. Profile row count, empty text, duplicates, languages, source groups, dates, and text-length distribution.

If the data materially exceeds reliable full-processing capacity, propose one of:

- a representative random sample, normally up to about 500 rows for an initial pass;
- a stratified sample across important time, channel, product, region, or customer groups;
- a user-defined filter;
- explicitly confirmed full processing with larger bounded batches.

Explain the coverage and inference trade-off. Apply sampling or filtering before partitioning and record the selected population.

## 3. Partition and analyze

Create bounded batch artifacts. Each semantic worker receives only the relevant batch reference, shared coding definitions, required output reference, and schema—not raw data embedded in the task description.

Each output row must retain the source identifier and contain structured labels, confidence, and concise evidence. Semantic classification must read the text in context; keywords may support retrieval or consistency checks but cannot substitute for judgment.

Use independent workers in parallel when available. Otherwise process the same persisted batches sequentially without changing the coding frame between batches.

## 4. Accept batch outputs

Validate each batch for:

- required columns and standard serialization;
- unique and complete source identifiers;
- allowed labels and parseable multi-value fields;
- input/output row reconciliation;
- nonempty evidence where required.

Retry only failed batches. After two unsuccessful attempts, use a controlled fallback for that batch or disclose the missing coverage; do not discard it silently.

## 5. Merge and synthesize

Merge accepted rows deterministically and recompute counts from the merged artifact. Distinguish frequency from severity and descriptive association from causation. Inspect low-confidence cases, rare but high-impact issues, and disagreements between batches.

The final output must state population and sample scope, coding definitions, processed coverage, counts or proportions with denominators, representative permitted evidence or paraphrases, uncertainty, limitations, and actionable follow-up questions.
