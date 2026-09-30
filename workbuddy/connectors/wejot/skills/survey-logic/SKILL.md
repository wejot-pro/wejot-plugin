---
name: survey-logic
description: Use when the user message or attachment contains runtime logic such as questionnaire jumps, termination, show/hide, mutual exclusion, max-choices, randomization, derived answers, option references, or dynamic candidate items; also used for modifying and accepting such logic.
---

## Applicable scenarios

Use this skill when the need involves **jump by option**, **same-page show/hide**, **"Other/None of the above" mutual exclusion inside multi-select**, **option references / dynamic candidate items**, **per-audience / per-module**, **low-score follow-ups**, **pre-submit data backfill**, **oscillation prevention**, **direct termination**, and other dynamic logic.

**Reading order**: generate the base preview → build requirement coverage and the logic TODO → determine the mode → search HTML to locate driver/target questions → read the `survey-ui.js` landing section → enter the corresponding chapter by mode to write code → independently review the final delivery.

---

## Before you start: four-step preparation

### Step 1 — Prepare the base preview first

For a new questionnaire, first use the host's survey-authoring workflow to generate a structurally valid
`survey-unified-generate.html` / `question_schema_generate.json` preview; reuse an existing valid preview when available.
After the preview is done, build the requirement coverage and logic TODO before any business-logic write.

### Step 2 — Generate the logic TODO

On first creation, when the logic TODO doesn't exist or is empty, delegate an independent sub-agent to read the source requirements in full and write the TODO. Let the host choose where the TODO is stored. If the user asks to execute an independent scenario, also pass this round's scenario scope and require that out-of-scope logic not enter the TODO; the sub-agent may still read surrounding source context, but its output list may cover only that scope. Only do full analysis when no scenario scope is specified.

Give the delegated sub-agent the source requirements, the scenario name when scoped, the trigger and target questions, and the acceptance contract. Ask it to record the selected scope and complexity in the TODO together with the runtime-logic list.

Read the TODO after the sub-agent returns. Its `scope` and `complexity` record the execution contract based on the specified scope (`full` when none is specified); the body structure is freely organized. When the TODO is non-empty, continue directly without delegating the analysis again; scenario resumption must not widen the scope merely because the source still contains other scenarios.

When candidate counts switch among auto-derived, manual-filled, and cleared states, the same state machine must cover the round-trip `0 -> 1 -> multiple -> 1 -> 0`. Treat this as complex logic and require an independent final review even when the question count is small or the condition copy is simple. Ordinary dynamic-candidate filtering does not become complex solely because the candidate count changes.

Implement the TODO item by item according to [`references/logic-todo-workflow.md`](references/logic-todo-workflow.md). The TODO is execution memory, not a questionnaire-persistence condition; a valid preview or version is not blocked merely because some later TODO items remain unfinished.

### Step 3 — Determine the mode

Run in the current survey workspace:

```bash
d="{current working directory}"; h="$d/survey-unified-generate.html"; j="$d/question_schema_generate.json"; [ ! -f "$h" ] || [ ! -f "$j" ] && echo SURVEY_MODE=CREATE || { grep -qE 'data-survey-mode="free"|LLM 自定义 CSS 区域 BEGIN' "$h" && echo SURVEY_MODE=FREE || echo SURVEY_MODE=STANDARD; }
```

| Command output | Logic code landing |
|------|------|
| `SURVEY_MODE=CREATE` | First use the available survey-authoring workflow to generate the form, then come back |
| `SURVEY_MODE=FREE` | `survey-ui.js` → `LLM 自定义交互逻辑区域 BEGIN/END` (legacy: HTML inline `<script>` custom area) |
| `SURVEY_MODE=STANDARD` | `survey-ui.js` → `业务逻辑扩展区 BEGIN/END` |

### Step 4 — Locate questions from HTML (true source)

**UUIDs and branch tokens are sourced from the current form's `survey-unified-generate.html`**; reusing strings from historical sessions or other questionnaires is forbidden. After multiple generate/append rounds, the constants at the top of `survey-ui.js` may drift from the HTML; always grep-verify before writing branches.

**Standard mode** (`.q[data-question]`, semantic `data-option-value`):

```bash
grep -n 'data-question-index="1"' survey-unified-generate.html
grep -A20 'data-question-index="1"' survey-unified-generate.html | grep -E 'data-question-uuid|data-option-value'
```

**Free mode** (no `.q` class, `data-option-value` often `"1"`/`"2"`/`"3"`):

```bash
grep -n 'data-question-index="1"' survey-unified-generate.html
grep -n 'data-code="Q1"' survey-unified-generate.html
grep -A10 'data-question-index="1"' survey-unified-generate.html | grep data-option-value
```

Long questionnaires: **forbidden to read the whole HTML file**; expand locally by question number or UUID. Question types/titles can be read from `question_schema_generate.json` for convenience, but **optionValue follows the HTML DOM**.

### Step 4 — Read the survey-ui.js landing section

```bash
grep -n "业务逻辑扩展区 BEGIN\|LLM 自定义交互逻辑区域 BEGIN" survey-ui.js
```

- Standard mode: the base's ~750 lines are read-only; logic is written only between BEGIN/END. For fixes or resets, inspect the local reference copy [`references/survey-ui.js`](references/survey-ui.js).
- The top of the standard mode may already have `Qn_UUID` / `Qn_OPT_n` / `resolveUuidByIndex` — **reference them directly; duplicate declarations are forbidden**; branch comparison values must still match the Step 3 HTML grep results.
- Prefer the API contracts already published by this skill and `survey-ui.js`; when the contract covers it, downloading or reading the full `survey-bridge.js` implementation source is forbidden. Only when the public contract cannot determine a behavior and correctness is affected may you grep/read the relevant implementation on demand (e.g. `setLogicQuestionVisibility` or bridge `buildSubmitData`), and only read the matched local parts.
- When API behavior is in doubt, grep/read: `setLogicQuestionVisibility` (template survey-ui.js), `data-logic-visible` submission filtering (bridge `buildSubmitData`).
- **Runtime bridge reference copy**: the `survey-bridge.js` linked from the questionnaire HTML (`SurveyDataBridge`: answer collection, submission, etc.) is available at [`references/survey-bridge.js`](references/survey-bridge.js). The file is long — **don't read it page by page**; to learn a specific behavior, search keywords such as `submit`, `submitAndStay`, `buildSubmitData`, `getAnswer`, or `data-logic-visible`, then inspect only the matching region.

### Long-code landing constraints

- Implement logic in small blocks by responsibility: constants/normalized reads, visibility, dynamic candidates, random assignment, and exposure recording are edited separately; run `node --check survey-ui.js` immediately after each edit.
- Forbidden: replacing the whole `survey-ui.js` in one edit, or assembling all questions and logic in one oversized execution. If syntax validation fails, only roll back and fix the latest block; never keep appending to a broken file.
- Prefer reading long Chinese stems and candidate options from the generated HTML/JSON and reusing them as arrays or canonical objects, avoiding nested quotes, ad-hoc substrings, and cross-segment string concatenation.

---

## Independent delivery review

For complex logic, delegate an independent sub-agent to re-check the final artifacts. The analysis pass that first extracts the TODO must not substitute for this final review. Give the reviewing sub-agent the original requirements, this round's scenario scope and acceptance contract, the current TODO, and the final `survey-unified-generate.html`, `question_schema_generate.json`, and `survey-ui.js` artifacts. Do not require a host-specific reviewer type, orchestration interface, evidence filename, or lifecycle tool.

After any fix, obtain a fresh independent review; do not reuse the old conclusion. The reviewing sub-agent must inspect the original requirements and the final HTML, JSON, and `survey-ui.js` together, and must not treat TODO text or code comments as implementation evidence. For matrix-driven logic, check both numeric and numeric-string scores. For derived or auto-recorded answers, check the `0 -> 1 -> multiple -> 1 -> 0` round-trip, including "multiple old candidates -> non-overlapping new unique candidates": each state first installs the current candidate pool with `setQuestionItems()`, then writes the unique derived value. Clear the single-candidate derived value when entering the multi-candidate manual state, while preserving manual answers still in the pool. A successful `setLogicAnswer(newValue)` atomically replaces an old radio selection; do not write a redundant `null` first.

For dynamic items, confirm the source uses normalized `getSelectedQuestionItems()` output instead of unpromised Bridge fields such as matrix `rowValue`. Confirm static placeholders disappear, actual candidates enter the target answer/exposure record, and every traceable candidate passed to `setQuestionItems()` carries `source` or `sourceKeys`. For signature-cached updaters, verify upstream code does not modify downstream state before calling an updater that may early-return; see [`references/demo.md`](references/demo.md) section 1.7.

If the review finds a defect, fix the concrete finding, re-run the relevant local checks, and delegate a fresh review of the changed artifacts. If independent delegation is unavailable, perform a clearly separated second-pass review against the same inputs and disclose that it was not independently delegated. Browser or device acceptance remains an external regression flow rather than a substitute for source-and-artifact review.

## Standard-mode logic

### Landing & constraints

- Code goes inside `业务逻辑扩展区 BEGIN/END`, registered via `window.SurveyRuntime.registerUserLogic()`.
- `registerUserLogic()` only registers callbacks; the base runs the callbacks uniformly in a microtask after `initSurvey()` completes and the current script call stack exits (falls back to a macrotask when microtasks are unsupported); **no need to listen for `DOMContentLoaded`**.
- Before the first callback execution, declare and initialize all state variables used by updaters (including signatures, derived answers, and caches), then call `fullRecalc()`; prefer placing state before the registration call for readability, but you cannot conclude TDZ merely because the state declaration sits after `registerUserLogic()`. Only when an actual execution path reads a variable before its `let`/`const` initialization does a `ReferenceError` temporary dead zone fire and break business logic.
- For show/hide logic, don't manually clear answers via DOM (e.g. `cb.checked = false`); just hide the question.
- Single/multi-select branch tokens must match the HTML **`data-option-value`**.

### Main API

| Method | Purpose |
|------|------|
| `SurveyRuntime.registerUserLogic(fn)` | Register business logic; auto-executes after init |
| `SurveyRuntime.onLogicAnswerChange(handler)` | Listen for `surveyAnswerChanged`; `detail.questionUuid` can filter |
| `SurveyRuntime.getLogicAnswer(uuid)` | Read an answer; common question-type values are in `.value`; single/multi-select additionally offer `optionValue(s)` |
| `SurveyRuntime.setLogicAnswer(uuid, value, opts?)` | Safely write or clear an answer; returns `{ ok, code?, questionUuid, questionType, answer?, cleared? }` |
| `SurveyRuntime.setQuestionContent(uuid, content)` | Update only the display copy of the stem/description; pass `null` to restore initial copy, empty string to clear; does not change schema or answers |
| `SurveyRuntime.setLogicQuestionVisibility(uuid, visible)` | Show/hide; writes `data-logic-visible`, syncs required asterisks/progress bar/pagination |
| `SurveyRuntime.setCheckboxOptionExclusivity(uuid, values)` | Configure mutually exclusive items inside a multi-select; the base handles state and bridge sync |
| `SurveyRuntime.getSelectedQuestionItems(uuid)` | Normalize single/multi-select selections or matrix-rated rows into stable items |
| `SurveyRuntime.setQuestionItems(uuid, items, opts?)` | Install dynamic items; for a standard catalog subset you may pass only `value`, the base fills label; `shuffle: true` for stable shuffle |
| `SurveyRuntime.getQuestionItemsExposure(uuid)` | Read dynamic items' actual exposure, order, source, and target slot |
| `SurveyRuntime.getStableRandomAssignment(key, variants)` | Stably draw one variant from variants; the returned `value` is a single element, never an array of permutations; if the element is an object, `assignment.value` is still that whole object, so read the object's fields afterward |
| `SurveyRuntime.submitSurvey()` | Async submit returning `Promise<{ ok, code, state, data?, details? }>`; the completion page is handled by the host |
| `SurveyRuntime.terminateSurvey(opts)` | Async screening termination returning the same structure; `data.keptQuestionUuids` lists kept questions |
| `SurveyRuntime.enableLocalDraftResume(opts?)` | Advanced: manually enable same-device draft resume (usually unnecessary, see below) |
| `SurveyRuntime.disableLocalDraftResume()` | Disable draft listening |
| `SurveyRuntime.onLocalDraftRestored(handler)` | Called once after draft answers and breakpoint page are fully backfilled; good for triggering a full recompute |
| `SurveyRuntime.clearLocalDraft()` | Clear the localStorage draft |

### Public command result contract

`submitSurvey`, `terminateSurvey`, and other mutators return structured results:

```json
{
  "ok": true,
  "code": "SURVEY_SUBMITTED",
  "state": "completed",
  "data": {}
}
```

On failure, `ok` is `false`, `code` points to a stable error code, and `state` is the post-failure questionnaire state; callers must await async commands and check `ok` — relying only on whether the completion page appears is insufficient.

When a cross-question reference targets matrix rows, custom items, ranking items, or other non-ordinary option targets, first read
[`references/logic-todo-workflow.md`](references/logic-todo-workflow.md)'s `DYNAMIC_ITEMS` and "dynamic item routing" sections; the root skill only provides the API index, not the adaptation protocol.
In that section, determine `BOUNDED_STANDARD` or `UNBOUNDED_GENERIC` first, then create the question type and write the logic; choosing an API first and patching the schema after failure is forbidden.

- When matrix answers come from the bridge, `row.score` may be a number or a numeric string; before comparing, filtering, or branching, you must use `const score = Number(row.score)` and validate with `Number.isFinite(score)`; strict type comparisons like `row.score === 1` are forbidden.

### Random assignment

- For random scenarios or copy variants, use `getStableRandomAssignment()`; pretending an in-memory counter from 0 is random or balanced is forbidden.
- For random order of dynamic options or matrix rows, use `setQuestionItems(..., { slot, shuffle: true })` directly; treating a single `value` from `getStableRandomAssignment()` as an array of permutations is forbidden.
- Use a stable, distinct `key` per independent random factor, and check the returned `ok`. Reuse the same key when recomputing over a fixed candidate pool; when the pool depends on answers, the key must include a pool signature built from the candidates' stable values sorted, recomputed at init and whenever any source question changes — see [`references/demo.md`](references/demo.md) section 1.12.
- Prefer passing a raw value array when only strings or numbers are needed; when objects carry extra metadata, first take the `assignment.value` object per [`references/demo.md`](references/demo.md) 1.12, then explicitly read its fields — directly comparing, concatenating, or passing objects to scalar-only APIs is forbidden.
- Dynamic versions must replace all respondent-visible related stems and descriptions; static placeholder copy contradicting the assignment result must not remain.
- The duplicate-prevention signature early-return must come before any downstream side effects. One updater owns and fully restores the visibility, items, answers, and copy it is responsible for; upstream must not reset these states first and then call an updater that may early-return on an old signature. When upstream reset is truly needed, invalidate the signature or force recomputation explicitly — see [`references/demo.md`](references/demo.md) section 1.7.
- This API guarantees stability within a single answering session, not exact cross-user quotas; when the requirement explicitly demands strict quota balancing, use server-side assignment — claiming it is implemented via frontend code is forbidden.

### Same-device breakpoint resume (coexisting with gates)

- Standard forms **have same-device drafts (answers + breakpoint page) disabled by default**; the switch is the business-extension-area constant `SURVEY_LOCAL_DRAFT_DEFAULT` (`true` = enabled).
- **Don't hand-write a whole localStorage draft in the business area**; gates still use `onLogicAnswerChange` + `setLogicQuestionVisibility`.
- After restore, the base backfills answers and `show(breakpoint page)`; gate listeners must be registered inside `registerUserLogic` so `surveyAnswerChanged` recomputes visibility.
- Logic depending on multiple restored answers should additionally use `onLocalDraftRestored()` for one full recompute; don't disable breakpoint resume just because logic code exists.
- **Same device only**; promising cross-device/device-change resume to users is forbidden.

**Show/hide must-haves**: must use **`SurveyRuntime.setLogicQuestionVisibility`**. **Forbidden**: the bridge-injected legacy global `window.setLogicQuestionVisibility` (= `SurveyApp.setVisibility`; only changes `style.display`, doesn't write `data-logic-visible`, so hidden questions still get submitted).

When a driver answer changes from answered to cleared, you must recompute too: after `getLogicAnswer()` returns an empty value, still explicitly restore each affected target question's hidden/default state. Using `if (!ans) return` before restoring state is forbidden — otherwise old visibility, dynamic items, derived answers, or hints linger. Minimal forms for single, multi-select, and rating are in [`references/demo.md`](references/demo.md) sections 1.1, 1.2, 1.6.

UUID resolution: use the injected **`Q1_UUID`** at the file top (= `resolveUuidByIndex(1)`); don't redeclare it in examples.

### Branch judgment quick reference

- **Single choice (8)**: `.optionValue` or `.value` (copy)
- **Multi-select (9)**: `.optionValues` array + `includes`; **forbidden** `.optionValue ===`
- **Rating (10)**: `.value` is a number; don't read `.optionValue`
- **Matrix (28)**: dynamic matrices read per the progressive reference's `.value` row-array contract
- In `getSelectedQuestionItems()`, `item.value` is the cross-question stable identity; when mapping the current question's catalog raw values, prefer `item.sourceValue` (old artifacts can fall back to `item.source.optionValue`); matrix scores read `item.meta.score`.
- **Custom (39)**: read `.value` by `answerKeys`; container `[data-survey-role="generic-container"][data-question-uuid]`

Minimal show/hide implementations for single choice and multi-select are in [`references/demo.md`](references/demo.md) sections 1.1, 1.2.

### Option mutual exclusion inside multi-select ("Other/None of the above/None")

`maxChoices` only limits count; it doesn't express mutual exclusion. Call the base API directly; re-listening to the DOM in the business area is forbidden.
Minimal call: [`references/demo.md`](references/demo.md) section 1.3.

When a question enables `otherOption`, the generator provides `Qn_OTHER_OPTION_VALUE`; don't guess "Other" as a regular option index `Qn_OPT_n`. For uncontrolled old artifacts, use the generic sentinel `"__other__"` so the base resolves the real value via `data-option-other`.

### Auto-recorded / derived answers

Use `setLogicAnswer` only when the requirement explicitly demands auto-recording, auto-selecting a unique candidate, or writing computed results. Calling `saveAnswerLocal` directly, modifying the bridge cache, or manually checking DOM is forbidden. Minimal derived/manual state switching: [`references/demo.md`](references/demo.md) section 1.4-C; candidate installation order in 1.4-B.

- RADIO(8): pass `optionValue`, or `{ optionValue, otherText? }`.
- CHECKBOX(9): pass `optionValue[]`, or `{ optionValues, otherTexts? }`.
- TEXTAREA(1): pass a string; SCALE(10): pass a score; MATRIX_SCALE(28): pass `[{ rowTitle, score }]`; GENERIC(39): pass an object.
- Passing `null` clears the UI, bridge cache, and hidden-submit markers, and dispatches an answer-change event.
- Success returns `{ ok: true, ... }`; failure returns `{ ok: false, code, questionUuid, questionType }` without changing existing answers. Callers must check `result.ok`; judging only object truthiness is insufficient.
- Hidden questions still don't submit by default. Only when the requirement explicitly asks for "background auto-record" use `{ submitWhenHidden: true }`; this flag only passes that question's derived answer, without changing other hidden-question filtering rules.
- All driver questions of auto answers must enter the TODO's "driver" and "state space"; recompute or clear when drivers change, so old answers don't linger after rollback.

### Conditional option references / dynamic candidate items

Applies to "bringing options or matrix rows from a previous question that meet the conditions into a later question". This is `DYNAMIC_ITEMS`; you must first read the progressive-disclosure reference's "dynamic item routing", determine `BOUNDED_STANDARD` or `UNBOUNDED_GENERIC`, then create the target question. The root skill keeps only three invariants: no direct mutation of item DOM; every item must have a stable `value`, standard types have the catalog fill in canonical `schemaLabel`, GENERIC explicitly provides label; the full chain must use `getSelectedQuestionItems()`, `setQuestionItems()`, and `getQuestionItemsExposure()`. Cross-question value mapping must use explicit `Map`s, arrays, or objects that are truly reachable in lexical scope; top-level `const`/`let` do NOT become `window` properties, and dynamic `window[...]` lookups for these constants are forbidden. Mapping: [`references/demo.md`](references/demo.md) section 1.4-A; candidate installation order in 1.4-B.

Stable randomization and answer coordination for dynamic items: [`references/demo.md`](references/demo.md) section 1.8. `setQuestionItems()` auto-preserves still-valid manual answers by stable value and clears invalidated answers; after a successful call, unconditionally calling `setLogicAnswer(uuid, null)` is forbidden. The standard form's actual candidates, order, and source are written into `data-question-item-exposure` and persisted with the answering snapshot; don't create hidden questions or extra answers to record duplicates; only model a separate answer field when the requirement explicitly specifies one. When one branch affects multiple dynamic target questions, every target must be updated separately — handling only one is not enough, see 1.11.

If the source requirement demands merging fully synonymous items, first build a source-item → canonical-candidate mapping in the logic TODO (`sourceKey`, `canonicalKey`, `schemaLabel`, `label`); when no evidence proves synonymy, use one-to-one mapping — writing special cases by keyword, question number, or title is forbidden. At runtime, merge by `canonicalKey` first, keep the source keys, then call `setQuestionItems`; display copy must use the full canonical `label` from the mapping — `substring` truncation or ad-hoc concatenation is forbidden; every item must carry `source` or `sourceKeys` to preserve exposure traceability. Minimal form: [`references/demo.md`](references/demo.md) section 1.9.

Minimal score-driven low-score follow-up: [`references/demo.md`](references/demo.md) section 1.6.

### Oscillation prevention for ordinary show/hide/jumps

Ordinary show/hide/jumps may take a signature of the driver answer to avoid repeated recomputation when `surveyAnswerChanged` fires repeatedly; minimal implementation: [`references/demo.md`](references/demo.md) section 1.7. The duplicate-prevention signature must cover all independent output states; when conditional hints migrate, the signature must include the current hint target, or sync the hint independently before any early-return that judges only branch values by content. Don't apply this example when calling `setQuestionItems()`; dynamic items must generate the signature from the normalized items' `value/schemaLabel/label` per the reference, and only commit the new signature after installation succeeds.

### Show/hide & jumps

- **Same-page show/hide**: `setLogicQuestionVisibility(uuid, visible)`
- **Cross-page jumps**: same-page stacking during generate (recommended); when unavoidable, `window._surveyPagination.show(pageIndex)`
- **Direct termination**: `SurveyRuntime.terminateSurvey({ keepQuestionUuids })`; calling `submitSurvey()` directly to bypass remaining required-question coordination is forbidden
- **In-form end persistence without jump** (optional): `SurveyDataBridge.submitAndStay({ answers })` — persists answers without triggering the host jump; use this API when showing the results page, don't drive jumps with `submitSurvey()`

Module guidance, recall scope, and answering criteria from the source material are visible question-surface requirements; they must land in the spec's question descriptions or via `setQuestionContent()`, not remain only in TODO, comments, or logic code. If a module's first question can be hidden by a branch, the hint must be placed on the first question visible on every path, and synced to the currently first-visible question as state changes, ensuring every legal branch sees it. The hint target must be decided by explicit branch state or real visibility; inferring visibility from "whether the entry question already has an answer" is forbidden, because the question can remain visible after the user manually answers.

When multiple sources require the user to choose a branch, before coding you must enumerate and implement the round-trip `single source -> multiple sources unanswered -> multiple sources answered -> single source -> no source`. While the branch-select question is unanswered or has returned to no-source, keep the branch-select question's correct visibility, and clear branch-dependent dynamic candidates, old answers, and exposure with `setQuestionItems(uuid, [], { slot })`; hiding DOM alone is not cleanup — a hidden question's old answers must not keep driving downstream. After a branch is chosen, install that branch's candidates first, then show the sub-questions; downstream updaters must not hide the still-awaiting-answer branch-select question in reverse. See [`references/demo.md`](references/demo.md) section 1.13.

### Custom question type (type=39)

- Follow the available component-authoring guidance: `data-answer-keys`, `submitGenericAnswer`, and the component's answer contract remain unchanged.
- Logic listening uses `onLogicAnswerChange` + `getLogicAnswer(uuid)`.
- Pre-submit backfill: `window.addEventListener('survey:before-submit', handler)`.

---

## Free-mode logic

**Mixing `SurveyRuntime` is forbidden** — free-mode `survey-ui.js` has no SurveyRuntime base; don't call the standard mode's `enableLocalDraftResume`.

### Same-device answer draft (skeleton default)

- New free-form skeletons restore **`state.answers` (answers)** from localStorage by default; **page number is not restored by default** (may stop at Q1 with options still selected).
- **Forbidden** to hand-write another answers draft in the LLM area.
- When the user explicitly asks to "stay on the original page": page navigation `notifyFreeDraftPage(n)` + `window.onFreeDraftPageRestore = (p) => showPage(p)`.
- Disable: `window.SURVEY_FREE_ANSWER_DRAFT_DEFAULT = false` (at the start of the LLM custom area).
- **Same device only**; promising cross-device resume is forbidden.

### Answer flow & landing

| Topic | Key points |
|------|------|
| Landing | `LLM 自定义交互逻辑区域 BEGIN/END` |
| Answers | options/input → `state.answers`; `surveyAnswerChanged` is **not** auto-dispatched |
| Listening | hook after base event handling, or wrap existing handlers; **can't** copy `onLogicAnswerChange` |
| UUID | `[data-question][data-question-index="N"]` or `data-code`; **not** `.q[...]` |
| optionValue | HTML is often `"1"`/`"2"`/`"3"`; align with `state.answers[uuid][].value` |
| Submit | `SurveyDataBridge.submit(buildAnswers(), document.documentElement.outerHTML)` |
| In-form end persistence | `SurveyDataBridge.submitAndStay({ answers: buildAnswers(), snapshot: false })` — persists without jumping to the host completion page; see [`references/submit-stay-pattern.md`](references/submit-stay-pattern.md) |

### Show/hide & buildAnswers

- Manage DOM show/hide yourself; sync `data-logic-visible="false"` on the question container (helps snapshots/debugging).
- **Must filter hidden questions in `buildAnswers()`** — when passing explicitly to `submit()`, the bridge won't auto-exclude by `data-logic-visible`. Minimal implementation: [`references/demo.md`](references/demo.md) section 2.1.

### Pagination

No `_surveyPagination`. When implementing pagination yourself in free mode, follow the contract: only RADIO(8) may auto-advance after selection; multi-select(9)/scale(10)/matrix(28)/GENERIC(39) advance via a "Next" button, and the button must bind click; a whole-form `[data-option]` click-to-page behavior is forbidden. Details: [`references/free-mode-skeleton-workflow.md`](references/free-mode-skeleton-workflow.md), section "Immersive pagination contract".

### Notes

1. HTML must keep the `survey-bridge.js` reference.
2. `data-*` contracts complete, so the bridge can collect answers.
3. **Forbidden** to bind auto-pagination to the whole form's `querySelectorAll('[data-option]')` — it would misfire on scale (10) and matrix (28).
4. `state.answers` format: single/multi-select `[{ label, value, selected: true }]`; scale **numbers**; matrix `[{ rowTitle, score }]`.
5. Judging "answered" must be by question type; using `answer.length` uniformly for all question types is forbidden.

---

## Logic scenario quick reference

| Scenario | Standard mode | Free mode |
|------|----------|----------|
| Same-page show/hide / exclusive modules | `onLogicAnswerChange` + `setLogicQuestionVisibility` | hook state.answers + DOM show/hide + buildAnswers filter |
| Option mutual exclusion in multi-select | `setCheckboxOptionExclusivity(uuid, values)` | normalize checked in base events before writing state.answers |
| Conditional option references | `setQuestionItems` + `getQuestionItemsExposure` | manage option DOM/state.answers in business area; submit exposure data in buildAnswers |
| Low-score follow-ups | read `.value`; dynamic matrix aligned with reference and exposure | read state.answers scores, manage show/hide yourself |
| Direct termination | `SurveyRuntime.terminateSurvey({ keepQuestionUuids })` | hide/filter remaining required questions, then call `submitSurvey()` / `SurveyDataBridge.submit(buildAnswers(), …)` |
| In-form end persistence | `SurveyDataBridge.submitAndStay({ answers, snapshot: false })` | same; show the in-form end DOM first, then persist — see [`references/submit-stay-pattern.md`](references/submit-stay-pattern.md) |
| Multi-module mutual exclusion | same-page stacking + batch `setLogicQuestionVisibility` | same-page stacking + batch DOM show/hide |
| Custom question pre-submit backfill | `survey:before-submit` | same (if the bridge is loaded) |
| Oscillation | answer-signature debounce | same |

---

## Implementation checklist

Before finishing complex logic, complete the independent delivery review described above. When an external dependency or requirement ambiguity cannot be resolved safely, stop and explain the decision needed from the user.

**Common**

- [ ] Step 1: read the independently prepared logic TODO
- [ ] Implemented item by item and synchronized the logic TODO status
- [ ] Composite branches cover positive, negative, and cleared states
- [ ] When driver answers are cleared, every downstream state explicitly restores hidden or business-default values
- [ ] Module hints and answering criteria from source material land on the actually visible surface of every legal branch
- [ ] Termination uses `terminateSurvey` with explicit kept questions
- [ ] Step 3: driver/target question UUIDs and `data-option-value` obtained from HTML grep
- [ ] Branch tokens come from the current form's HTML, not historical-session strings
- [ ] After modifying the spec and regenerating, cross-check UUID/optionValue between HTML and logic code
- [ ] Multi-select mutual exclusion uses the base API; `maxChoices` not treated as an exclusion rule
- [ ] Option references are filtered, mapped, deduped first; use full canonical label, stable unique value, and source/sourceKeys, landed via `setQuestionItems`
- [ ] All dynamic target questions affected by one branch are updated separately; no mixed candidate leftovers
- [ ] Single/multi-source branches cover unanswered and back-to-edit; uncleared sub-question candidates, answers, and exposure when no branch chosen
- [ ] Downstream candidates/copy read only currently valid and visible branch answers, not hidden questions' old answers
- [ ] Answer-driven randomization recomputes at init and on every source-question change; key includes the normalized candidate-pool signature
- [ ] Handled target-question visibility when dynamic candidates are empty; when exposure data needs analysis, its persistence semantics verified

**Standard mode**

- [ ] Logic only inside `业务逻辑扩展区 BEGIN/END`
- [ ] Show/hide uses `SurveyRuntime.setLogicQuestionVisibility`, not the legacy global

**Free mode**

- [ ] Logic in `LLM 自定义交互逻辑区域`; no SurveyRuntime calls
- [ ] `buildAnswers()` excludes questions with `data-logic-visible="false"`

---

## Efficient code reading

```bash
grep -n "业务逻辑扩展区 BEGIN" survey-ui.js
grep -n "LLM 自定义交互逻辑区域 BEGIN" survey-ui.js
```

After locating line numbers, read only a bounded landing section; don't load the whole `survey-ui.js` at once. Use the local copies in [`references/survey-ui.js`](references/survey-ui.js), [`references/survey-bridge.js`](references/survey-bridge.js), and [`references/sortable.js`](references/sortable.js) for narrow source inspection. Do not repeatedly download or fully read these long dependencies.
