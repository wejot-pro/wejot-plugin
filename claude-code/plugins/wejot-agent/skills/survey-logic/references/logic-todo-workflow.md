# Questionnaire Logic TODO Workflow

## 1. TODO is execution memory

The logic TODO records the questionnaire logic in the source requirements that needs runtime execution, plus current implementation progress. Its header should keep `scope` and `complexity`; the body is not a machine protocol and requires no fixed IDs, fields, tables, path, or wording.

On first creation, delegate an independent sub-agent to read the source requirements in full and write the TODO in a host-selected location. The implementing agent reads the list and starts building the form; it does not re-scan the source to generate a second list.

The list only needs to let the implementer see:

- what input or state triggers a change;
- which questions, options, answers, or submit behaviors change;
- what to restore or clear when switching from one state to another;
- which items are done and which are still pending.

You may use checkboxes, plain lists, tables, or grouped headings. After implementing an item, update the original entry directly; don't rewrite the whole file for formatting.

## 2. Continue from existing progress each round

When the TODO is non-empty, read it first, then check the existing HTML, JSON, and `survey-ui.js`. When questionnaire artifacts exist, only fix or continue current items; don't re-parse the source, rebuild question UUIDs, or overwrite already-correct logic.

When the user says "continue" or "OK, continue", continue from the first unfinished group. After finishing a group, update the same logic TODO, produce a new previewable version, then ask the user to confirm the effect.

When there is lots of logic, batch it by dependency, keeping each batch within a user-verifiable scope. The implementing agent decides the batches; no fixed count or fixed tables are required.

## 3. Check complete state when implementing

Logic depending on answer state should be handled by one idempotent recompute function covering at once:

1. page init or draft restore;
2. driver answer changes;
3. driver answer cleared;
4. switching from branch A to branch B, then back from B to A.

Each recompute writes the complete output this logic owns; avoid implementing only "show when the condition is met" while missing the hide, candidate removal, or derived-answer clearing after the condition lapses.

### Dynamic items

When "bringing a previous question's selected items into a later question", first decide whether candidate identity can be enumerated at form-creation time:

- enumerable: pre-declare the full candidate set in the same target question and switch the actually exposed items at runtime;
- not enumerable: use a custom item type that supports dynamic identity;
- when the source allows "Other", pass the user-entered text and its stable identity along.

The implementation order is fixed: compute valid sources and candidates → install candidates → write or clear the derived answer → update visibility.

When the requirement also asks to "merge fully synonymous items", first build a source-item → canonical-candidate mapping table in the TODO, then implement the runtime logic. The mapping table must contain at least a stable `sourceKey`, a stable `canonicalKey`, `schemaLabel`, and the display `label`; without evidence of synonymy, use one-to-one mapping, don't guess by keywords or question numbers. At runtime, merge by `canonicalKey` first, then hand each canonical candidate's `value` to `setQuestionItems`, and keep the source keys in `source`/`meta` so answers and exposure records remain traceable. This flow applies to options, matrix rows, and GENERIC items; it is not tied to a specific questionnaire or question number.

### Derived answers

When the target question may switch between auto-filled and user-filled, distinguish answer ownership:

- write the derived answer when entering the derived state;
- when leaving the derived state, only clear the old derived answer;
- after entering the manual state, keep the user's newly filled answer;
- when the source is empty or invalid, remove the corresponding candidates and residual values.

### Show/hide & mutual exclusion

- Standard-mode show/hide uses `SurveyRuntime.setLogicQuestionVisibility`;
- multi-select mutual exclusion uses `SurveyRuntime.setCheckboxOptionExclusivity`;
- whether hidden questions keep or submit answers follows the user's original requirement;
- "end the questionnaire" and "hide later questions" are different effects and must not replace each other.

## 4. Completion and confirmation

After writing code, first check UUIDs, optionValue, event entry points, and reverse cleanup against the current HTML and `survey-ui.js`, then update the corresponding TODO.

Before final delivery, re-check the original requirement, the TODO, and the actual implementation side by side, judging item by item whether the effects the user asked for are fully implemented. The TODO body's format, fields, and wording do not participate in completion judgment; `scope` confirms the work has not overrun and `complexity` determines the review depth. When omissions are found, add items directly and continue implementing.

Static checks only show the script can load. For page behaviors needing user judgment, hand the new preview version of that batch to the user for confirmation; unconfirmed items may be marked "implemented, awaiting confirmation".
