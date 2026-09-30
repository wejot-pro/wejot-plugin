# Questionnaire Logic Examples

This file only provides minimal implementation forms. Before use, you MUST verify UUIDs, question types, and
`data-option-value` against the current questionnaire HTML; the `Qn_UUID`, `Qn_OPT_n` in the examples are placeholder names.

The underlying functions like `SurveyDataBridge` and `saveAnswerLocal` are implemented in the externally linked
`survey-bridge.js`. That file is large and is a private implementation; downloading, reading it fully, or relying on its internal fields is forbidden;
standard-mode business logic only uses the `SurveyRuntime` public API. When matrix-driven dynamic items are used, consume
the normalized result of `getSelectedQuestionItems()`; don't read the un-promised `rowValue` from the bridge.

## 1. Standard mode

<a id="pattern-runtime-init-order"></a>

### 1.0 Initialization order

`registerUserLogic()` itself only puts the callback into the registry; it doesn't execute synchronously. During initialization, `runUserLogic()` is called uniformly in a microtask after the current script finishes executing (falls back to a macrotask when microtasks are unsupported). Therefore, a reviewer must judge whether the "first callback actual execution point" is later than the `let`/`const` initialization — you cannot conclude TDZ merely because the state declaration sits after the registration call. Inside the callback, still declare and initialize the state the updaters depend on (signatures, derived answers, caches) first, then run the first full recompute; only when an execution path really reads a variable before initialization does a `ReferenceError` fire.

```javascript
let lastSignature = null
let derivedValue = null

function recalcAll() {
  // only here do we read lastSignature / derivedValue and run downstream updates
}

recalcAll()
window.SurveyRuntime.onLocalDraftRestored(recalcAll)
```

<a id="pattern-radio-visibility"></a>

### 1.1 Single-choice-driven show/hide

```javascript
window.SurveyRuntime.onLogicAnswerChange(detail => {
  if (detail.questionUuid !== Q1_UUID) return
  const ans = window.SurveyRuntime.getLogicAnswer(Q1_UUID)
  window.SurveyRuntime.setLogicQuestionVisibility(
    Q2_UUID,
    Boolean(ans && ans.optionValue !== Q1_OPT_NEVER)
  )
})
```

When the driver answer is cleared, `getLogicAnswer()` returns an empty value; you must still explicitly restore the target question to hidden or its business default state;
using `if (!ans) return` before the show/hide call to leave old state is forbidden.

<a id="pattern-checkbox-visibility"></a>

### 1.2 Multi-select-driven show/hide

```javascript
window.SurveyRuntime.onLogicAnswerChange(detail => {
  if (detail.questionUuid !== Q1_UUID) return
  const ans = window.SurveyRuntime.getLogicAnswer(Q1_UUID)
  const show = Boolean(ans && ans.optionValues && ans.optionValues.includes(Q1_OPT_1))
  window.SurveyRuntime.setLogicQuestionVisibility(Q2_UUID, show)
})
```

<a id="pattern-checkbox-exclusivity"></a>

### 1.3 Mutual exclusion inside multi-select

```javascript
window.SurveyRuntime.setCheckboxOptionExclusivity(Q2_UUID, [Q2_OTHER_OPTION_VALUE])
```

The base handles exclusivity normalization before the `maxChoices` limit; after reaching the limit, clicking the special item still clears ordinary items and keeps the special item. So here you only register the exclusivity relation — there is no need to listen to answer length or rewrite answers separately.

<a id="pattern-derived-manual"></a>

### 1.4 Derived answers and manual answers switching

This section consists of four composable patterns. A reviewer should cite the most specific subsection by defect type; don't cite only the general section `1.4`.

<a id="pattern-source-target-map"></a>

#### 1.4-A Explicit mapping from source values to the target catalog

Cross-question derivation first maps the source question's stable values to values that really exist in the target question's catalog. The mapping must live in the current
lexical scope; you can't concatenate variable names and guess from `window`.

```javascript
let derivedB2Value = null
const B2_SOURCE_UUIDS = new Set([B1_UUID])

// Use explicit mapping in lexical scope. Top-level const/let do not become window properties;
// don't dynamically read these constants via window['B2_OPTION_' + index], otherwise you get undefined.
const targetValueBySource = new Map([
  [B1_SOURCE_VALUE_1, B2_OPTION_VALUE_1],
  [B1_SOURCE_VALUE_2, B2_OPTION_VALUE_2],
])

function collectActualProblemValues() {
  return window.SurveyRuntime.getSelectedQuestionItems(B1_UUID)
    .filter(item => Number(item.meta && item.meta.score) >= PROBLEM_SCORE_MIN)
    .map(item => item.sourceValue || (item.source && item.source.optionValue))
    .map(sourceValue => targetValueBySource.get(sourceValue))
    .filter(Boolean)
}
```

<a id="pattern-candidate-install-before-answer"></a>

#### 1.4-B Install the candidate pool first, then write the derived answer

Each state first installs the current candidate pool. Otherwise, going straight from candidates A/B to the unique candidate C,
`setLogicAnswer(C)` returns `OPTION_NOT_FOUND` because C hasn't entered the target question's DOM yet.

```javascript
function installB2Candidates(actualProblemValues) {
  const itemsResult = window.SurveyRuntime.setQuestionItems(
    B2_UUID,
    actualProblemValues.map(value => ({ value })),
    { slot: 'options' },
  )
  if (!itemsResult.ok) {
    console.warn('B2 candidates failed', itemsResult)
    return null
  }
  return itemsResult
}
```

<a id="pattern-derived-manual-transition"></a>

#### 1.4-C Derived and manual ownership over 0/1/multiple candidates

`0` candidates clear the old value and hide; `1` candidate is written by logic and hidden; multiple candidates enter the manual state, where only old derived values held by the business logic are cleared and still-valid manual answers are kept.

```javascript
function syncDerivedB2() {
  const actualProblemValues = collectActualProblemValues()
  if (!installB2Candidates(actualProblemValues)) return

  const current = window.SurveyRuntime.getLogicAnswer(B2_UUID)
  if (actualProblemValues.length === 0) {
    derivedB2Value = null
    if (current) {
      const clearResult = window.SurveyRuntime.setLogicAnswer(B2_UUID, null)
      if (!clearResult.ok) console.warn('B2 stale answer clear failed', clearResult)
    }
    window.SurveyRuntime.setLogicQuestionVisibility(B2_UUID, false)
    return
  }

  if (actualProblemValues.length === 1) {
    derivedB2Value = actualProblemValues[0]
    // setLogicAnswer atomically overwrites the old single-choice answer; once candidate C is installed, no need to write null first.
    const answerResult = window.SurveyRuntime.setLogicAnswer(B2_UUID, derivedB2Value, {
      submitWhenHidden: true,
    })
    if (!answerResult.ok) {
      derivedB2Value = null
      console.warn('B2 derived answer failed', answerResult)
    }
    window.SurveyRuntime.setLogicQuestionVisibility(B2_UUID, false)
    return
  }

  if (derivedB2Value !== null && current && current.optionValue === derivedB2Value) {
    const clearResult = window.SurveyRuntime.setLogicAnswer(B2_UUID, null)
    if (!clearResult.ok) console.warn('B2 derived answer clear failed', clearResult)
  }
  derivedB2Value = null
  window.SurveyRuntime.setLogicQuestionVisibility(B2_UUID, true)
}
```

<a id="pattern-listener-self-write-restore"></a>

#### 1.4-D Listeners, self-write-back, and draft restore

All source listeners, initial sync, and draft restore reuse the same idempotent updater. Walk the listener call chain to check whether the updater
would write back the triggering question itself, avoiding manual answers being cleared in the same change chain or forming a self-oscillating loop.

An answer-change event alone cannot prove manual ownership: the business logic's own `setLogicAnswer` writes or clears may also enter the same change chain. Don't turn a boolean flag into the manual state just because the target question fires `onLogicAnswerChange`; instead, first record the concrete derived value this logic holds as in 1.4-C, then clean up only when the current answer still equals that derived value. This way, on draft restore, valid manual answers without a derived-ownership record are naturally kept.

```javascript
window.SurveyRuntime.registerUserLogic(() => {
  window.SurveyRuntime.onLogicAnswerChange(detail => {
    if (B2_SOURCE_UUIDS.has(detail.questionUuid)) syncDerivedB2()
  })
  window.SurveyRuntime.onLocalDraftRestored(syncDerivedB2)
  syncDerivedB2()
})
```

Only clear derived values written by the business logic. After entering the multi-candidate manual state, later candidate-pool recomputations should keep still-valid
manual answers; when switching from a single candidate to multiple candidates, you must clear the old derived value so it doesn't masquerade as a user choice.
The same rule applies to the "single-branch auto-record, multi-branch show question" scenario. Initial execution, source answer changes,
and draft restore must reuse the same idempotent updater; a state machine written as a top-level one-shot snippet is not allowed.

<a id="pattern-draft-restore-recalc"></a>

### 1.5 Full recompute after breakpoint restore

Breakpoint restore does not disable business logic. If logic depends on the joint state of multiple questions, register a restore-completed callback
and recompute once after all answers and the breakpoint page are backfilled; the callback should reuse the same idempotent function as initialization.

```javascript
function recalcAll() {
  // read current answers and call setLogicQuestionVisibility / setQuestionItems as needed
}

window.SurveyRuntime.registerUserLogic(() => {
  recalcAll()
  window.SurveyRuntime.onLocalDraftRestored(recalcAll)
})
```

<a id="pattern-scale-followup"></a>

### 1.6 Score-driven low-score follow-up

The threshold `6` in this example only illustrates the comparison location; it is not a default business rule. When implementing, replace it per the source requirement and
current scale range; e.g. a five-point scale cannot reuse this number.

```javascript
window.SurveyRuntime.onLogicAnswerChange(detail => {
  if (detail.questionUuid !== Q1_UUID) return
  const ans = window.SurveyRuntime.getLogicAnswer(Q1_UUID)
  window.SurveyRuntime.setLogicQuestionVisibility(Q2_UUID, Boolean(ans && ans.value <= 6))
})
```

<a id="pattern-idempotent-signature"></a>

### 1.7 Idempotent signature for ordinary show/hide

The signature must include all business values that change downstream results. Matrix-driven logic must sign not only row IDs but each row's
`score`; otherwise returning to edit the same row's score won't recompute. Dynamic-item signatures must include the normalized
items' `value`, `schemaLabel`, and `label`, and only commit the new signature after installation succeeds.

The signature early-return must happen before any downstream side effect. Let the updater own the downstream state it is responsible for; upstream hiding/clearing
downstream and then calling an updater that may return directly on an old signature is forbidden. Otherwise unrelated answer changes leave
originally valid downstream state in a temporary reset state. When upstream reset is truly needed, set that updater's signature to
`null` first, or provide an explicit force-recompute parameter.

The initial sentinel must not equal any legal business state's signature; in particular, don't use an empty string for both "not yet computed"
and "currently unanswered". Prefer `null` or a unique value no signature function can return. The first full recompute must actually execute so the default visibility, items, answers, and copy sync to the currently unanswered state.

```javascript
let lastSig = null
window.SurveyRuntime.onLogicAnswerChange(detail => {
  if (detail.questionUuid !== Q1_UUID) return
  const items = window.SurveyRuntime.getSelectedQuestionItems(Q1_UUID)
  const sig = JSON.stringify(items.map(item => ({
    value: item.value,
    schemaLabel: item.schemaLabel,
    label: item.label,
    score: item.meta && item.meta.score,
  })))
  if (sig === lastSig) return
  // `2` is only an example threshold; must be replaced per the current requirement and scale range.
  const visible = items.some(item => Number(item.meta && item.meta.score) <= 2)
  window.SurveyRuntime.setLogicQuestionVisibility(Q2_UUID, visible)
  lastSig = sig
})
```

<a id="pattern-dynamic-items-stable-shuffle"></a>

### 1.8 Dynamic items stable shuffle and answer coordination

When dynamic items need a random order, hand the normalized items directly to `setQuestionItems`. `shuffle: true`
keeps the order stable within the same answering session and on draft restore. The base preserves still-existing manual answers by stable `value`
and clears answers no longer in the candidate set; after success, don't unconditionally clear the target question's answer.

When the full candidate catalog of standard single-choice, multi-select, and matrix rows is already declared in the schema, passing `{ value }` suffices;
the base fills in the label from the catalog. Only explicitly pass `label` when changing display copy, mapping by `schemaLabel`, or using GENERIC
unbounded items; new values outside the catalog are still rejected.

After successful installation on a standard form, the base writes the actual candidates, order, and `source`/`sourceKeys` into
`data-question-item-exposure`, persisted with the answering snapshot on submit. Business logic need not create hidden questions or extra answers
to duplicate exposure lists, order, or counts; only model a separate answer field when the requirement explicitly specifies one.

```javascript
const items = candidates.map(item => ({
  value: item.value,
  label: item.label,
  schemaLabel: item.schemaLabel,
  source: item.source,
}))
const itemsResult = window.SurveyRuntime.setQuestionItems(Q2_UUID, items, {
  slot: 'options',
  shuffle: true,
})
if (!itemsResult.ok) console.warn('Q2 dynamic items failed', itemsResult)
```

`getStableRandomAssignment(key, variants)` only draws one stable version from `variants`, suitable for scenario or
copy-version assignment; its returned `value` is not an array of permutations and can't be used for dynamic-item shuffling.

<a id="pattern-canonical-merge"></a>

### 1.9 Canonical merge of dynamic candidate items

First, the logic TODO determines a `canonicalKey` for each source item; when no provable synonymy exists, canonical keys map one-to-one with source keys. At runtime, merge by canonical key and keep sources for analysis and exposure-record traceability:

```javascript
const canonicalItems = new Map()
for (const source of sources) {
  const mapping = SOURCE_TO_CANONICAL[source.sourceKey]
  if (!mapping) continue
  const current = canonicalItems.get(mapping.canonicalKey)
  if (current) {
    current.sourceKeys.push(source.sourceKey)
    continue
  }
  canonicalItems.set(mapping.canonicalKey, {
    value: mapping.value,
    label: mapping.label,
    schemaLabel: mapping.schemaLabel,
    sourceKeys: [source.sourceKey],
  })
}
const result = window.SurveyRuntime.setQuestionItems(
  TARGET_UUID,
  Array.from(canonicalItems.values()).map(item => ({
    ...item,
    source: item.sourceKeys,
  })),
  { slot: 'options', shuffle: true },
)
if (!result.ok) console.warn('canonical dynamic items failed', result)
```

<a id="pattern-terminate-completion"></a>

### 1.10 Screening termination submit

When a termination condition is hit, don't call `submitSurvey()` directly. Use `terminateSurvey` to explicitly keep the screening questions
and hide the remaining required questions.
`SCREENING_QUESTION_UUIDS_TO_KEEP` is a placeholder and must be defined per the current
termination branch's submit contract; you can't assume only the triggering question is kept.

```javascript
// this branch lives in an async answer-change handler
if (answer.optionValue === Q1_OPT_TERMINATE) {
  const result = await window.SurveyRuntime.terminateSurvey({
    keepQuestionUuids: SCREENING_QUESTION_UUIDS_TO_KEEP,
  })
  if (!result.ok) console.warn('terminate survey failed', result)
  return
}
```

<a id="pattern-conditional-dynamic-items"></a>

### 1.11 All dynamic items of a conditional branch

When one branch simultaneously changes matrix rows, single-choice options, and multi-select options, each target must independently call
`setQuestionItems`. Updating only one target while other questions keep two sets of candidates is not acceptable.

```javascript
const branch = getBranch()
const rowsResult = window.SurveyRuntime.setQuestionItems(Q2_UUID, ROWS[branch], {
  slot: 'matrixRows',
})
const optionsResult = window.SurveyRuntime.setQuestionItems(Q3_UUID, OPTIONS[branch], {
  slot: 'options',
})
if (!rowsResult.ok || !optionsResult.ok) {
  console.warn('branch items failed', { rowsResult, optionsResult })
  return
}
```

<a id="pattern-stable-random-assignment"></a>

### 1.12 Answer-driven stable random recompute

When the random pool depends on answers, the stable assignment's key must include the normalized candidate-pool signature and recompute on every source-question change. This way first fill-in, back-to-edit, and draft restore all get a stable result consistent with the current candidate pool.
When the candidate pool is empty, don't call it; when there is only one candidate, the base directly returns that candidate, no business-code branch needed.

```javascript
function recomputeScenario() {
  const variants = buildVariantsFromAnswers()
  if (variants.length === 0) return
  const poolSig = JSON.stringify(
    variants.map(item => item.value).sort((a, b) => String(a).localeCompare(String(b))),
  )
  const assignment = window.SurveyRuntime.getStableRandomAssignment(
    `scenario:${poolSig}`,
    variants,
  )
  if (!assignment.ok) return
  // when variants is an object array, assignment.value is still the full selected object.
  const selected = assignment.value
  const scenarioValue = selected.value
  window.SurveyRuntime.setQuestionContent(TARGET_UUID, {
    title: buildScenarioTitle(scenarioValue),
  })
}

window.SurveyRuntime.onLogicAnswerChange(detail => {
  if (!SOURCE_UUIDS.includes(detail.questionUuid)) return
  recomputeScenario()
})
recomputeScenario()
```

If the business only needs a scalar, passing a scalar array directly is more concise:

```javascript
// The key, candidate values, and "updated at" copy in this example only demo scalar consumption; replace with the current business definition.
const assignment = window.SurveyRuntime.getStableRandomAssignment(
  'time-version',
  ['1', '5', '10'],
)
if (!assignment.ok) return
const title = `Updated ${assignment.value} minutes ago`
```

<a id="pattern-module-prompt-migration"></a>

### 1.13 Conditional module prompt migration

When a module's entry question may be auto-answered and hidden, sync the module prompt to the current first-visible question; don't write the prompt only on an entry question that may be hidden. Whether the entry question is visible must come from explicit branch state or real visibility; you can't substitute whether `getLogicAnswer()` has an answer for it: a visible entry question remains visible after the user manually answers it. When a branch allows back-to-edit, also clear non-target questions' old copy at the same time, so the prompt doesn't duplicate after migrating from one target to another. The prompt target is an independent output state: prompt sync must execute before any early-return that judges only branch values by content, or include `promptTarget` in the duplicate-prevention signature.

```javascript
function syncModulePrompt(entryVisible) {
  const promptTarget = entryVisible ? ENTRY_UUID : NEXT_VISIBLE_UUID
  for (const uuid of [ENTRY_UUID, NEXT_VISIBLE_UUID]) {
    window.SurveyRuntime.setQuestionContent(uuid, {
      description: uuid === promptTarget ? MODULE_PROMPT : null,
    })
  }
  return promptTarget
}

// only applies to the business rule "candidate count decides entry visibility"; don't infer from whether the entry question already has an answer.
// For other rules, compute entryVisible from explicit branch state in the source requirement.
const entryVisible = sourceCandidates.length > 1
const promptTarget = syncModulePrompt(entryVisible)
const signature = JSON.stringify({ branchValue, promptTarget })
```

<a id="pattern-branch-selection-cleanup"></a>

### 1.14 Multi-source branch selection and sub-question cleanup

With multiple sources, the branch-select question itself and the downstream questions depending on the chosen branch are two independent outputs. While nothing is chosen, keep the entry; downstream update functions must not hide the entry again just because there is no `selectedBranch`. Hiding sub-questions alone doesn't clear old candidates, answers, or exposure; when no branch is chosen, clean up uniformly with an empty candidate pool, and later aggregations must not read these hidden questions:

```javascript
const BRANCH_CHILD_SLOTS = new Map([
  [BRANCH_MATRIX_UUID, 'matrixRows'],
  [BRANCH_RADIO_UUID, 'options'],
  [BRANCH_CHECKBOX_UUID, 'options'],
])

function clearBranchChildren() {
  for (const [uuid, slot] of BRANCH_CHILD_SLOTS) {
    window.SurveyRuntime.setLogicQuestionVisibility(uuid, false)
    const result = window.SurveyRuntime.setQuestionItems(uuid, [], { slot })
    if (!result.ok) console.warn('branch child clear failed', { uuid, result })
  }
}

function syncBranchQuestions(sourceCount) {
  // only applies to the business rule "single source auto-derives, multiple sources require manual choice".
  // Other branch-ownership rules must be rewritten per the source requirement, not applied by sourceCount alone.
  const selectedBranch = sourceCount === 1 ? deriveOnlyBranch() : getBranchAnswer()
  window.SurveyRuntime.setLogicQuestionVisibility(BRANCH_UUID, sourceCount > 1)

  if (sourceCount > 1 && !selectedBranch) return clearBranchChildren()
  if (sourceCount === 0) return clearBranchChildren()

  for (const [uuid, slot] of BRANCH_CHILD_SLOTS) {
    const items = ITEMS_BY_BRANCH[selectedBranch][uuid]
    const result = window.SurveyRuntime.setQuestionItems(uuid, items, { slot })
    if (!result.ok) {
      console.warn('branch child install failed', { uuid, result })
      clearBranchChildren()
      return
    }
  }

  for (const [branch, uuids] of Object.entries(BRANCH_CHILDREN)) {
    for (const uuid of uuids) {
      window.SurveyRuntime.setLogicQuestionVisibility(uuid, branch === selectedBranch)
    }
  }
}
```

`setQuestionItems(..., [])` synchronously clears answers that no longer exist and updates exposure per the base contract, so don't additionally
unconditionally clear still-valid manual answers. When building downstream candidates, also compute the same `branchReady` first; when false,
return an empty set directly — don't read hidden sub-questions' old answers just because the module source still exists.

## 2. Free mode

<a id="pattern-free-hidden-answer-filter"></a>

### 2.1 Filter logic-hidden questions on submit

```javascript
function buildAnswers() {
  const hidden = new Set(
    Array.from(document.querySelectorAll('[data-question][data-logic-visible="false"]'))
      .map(el => el.getAttribute('data-question-uuid'))
      .filter(Boolean)
  )
  return [
    // ... each question entry, skipping questions where hidden.has(uuid)
  ]
}
```
