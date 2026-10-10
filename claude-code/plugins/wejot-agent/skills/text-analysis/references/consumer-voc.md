# Consumer VOC Six-Step Closed Loop

Use this specialized flow for consumer products, retail, FMCG, consumption experience, or brand VOC.

Before full execution, explain the six intended deliverables, material sampling choices, and privacy limitations. Obtain explicit user confirmation because this workflow goes beyond ordinary theme coding into response design, requirement translation, and follow-up planning.

## 1. Collect and screen

Define the screening frame and classify each record by value, relevance, sentiment, severity, category, and routing. Keep noise visible in the audit rather than deleting it silently.

Keywords may explain the frame but must not perform the actual classification. A semantic reviewer must read the feedback in context. Preserve the stable VOC identifier, original source, date, and permitted context.

Profile volume before batching. If the data is unusually large, propose a representative sample of about 500 rows, a stratified sample, a user-defined filter, or explicitly confirmed full processing. Apply the decision before partitioning and disclose the final coverage.

## 2. Decode

For high-value VOC, separate three layers:

- **Literal or rhetorical:** core entities, attributes, events, and feature statements after removing decorative wording.
- **Pragmatic:** situation, intent, motivation, unmet need, barrier, behavior pattern, and expected outcome.
- **Cultural or category:** shared meaning, social signal, category convention, or collective pattern supported by the text.

Return source identifier, original permitted evidence, sentiment, themes, feature points, motivations, behavior patterns, cultural signals, severity, and confidence. Do not infer cultural meaning from stereotypes or unsupported demographics.

## 3. Frame

Aggregate decoded evidence into a research framework of dimensions, key questions, supporting VOC signals, scene details, and affected user groups. Preserve minority and emerging signals instead of forcing every record into dominant themes.

## 4. Respond

For high-priority feedback, produce a response map containing source identifier, issue, response strategy, emotional tone, key goal, directly usable response draft, next action, and expected outcome. Separate a proposed response from an assertion that the business has acted.

The framing and response work are independent after decoding and may run concurrently when the host supports independent workers.

## 5. Translate

Create a need-translation table that connects:

`source VOC -> user need -> measurable engineering or service requirement -> threshold/unit -> validation method -> product or operating decision -> owner`

User language must be traceable to actual feedback. Parameters must be measurable, validation methods executable, and decisions implementable. Mark unknown values instead of inventing thresholds.

## 6. Grow and close the loop

Create a tracking record with source identifier, core need, proposed response, improvement plan, owner, target date, verification population, metric and denominator, review cadence, closure status, final evidence, and observed business impact.

Do not claim closure or impact before evidence exists. Define what future observation would support improvement and what decision follows from success or failure.

## Batch and acceptance contract

Persist the shared frame, partition prepared data into bounded batches, and preserve one output row per stable identifier. Use independent workers in parallel when available; otherwise process the same batches sequentially. Task descriptions should carry artifact references and schemas rather than raw feedback.

Validate required fields, unique identifiers, allowed labels, serialization, and input/output coverage before merging. Retry only failed batches; after repeated failure, use a controlled fallback or disclose the gap.

## Final deliverables

Return or reference:

- screening results and coverage summary;
- decoded row-level evidence;
- research framework;
- response map;
- need-translation table;
- growth/closure tracker;
- coding definitions, limitations, privacy treatment, sampling disclosure, and unresolved questions.
