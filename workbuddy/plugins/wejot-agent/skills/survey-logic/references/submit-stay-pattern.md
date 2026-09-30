# In-form ending persistence (submitAndStay)

After answering, show an ending page in the questionnaire (thank-you page / results summary / custom poster, etc.) while persisting the answers, **without** triggering host hiding or a jump to the generic completion page.

## When to use

- The user wants "collect answers + in-form poster/ending/result display, submit without jumping away"
- The user wants "in-form ending / result / poster, submit without jumping away"
- The last screen is in-form custom DOM

## Interface

`SurveyDataBridge.submitAndStay(opts)`

| Difference from `submit()` | Description |
|---|---|
| Message | sends `SUBMIT_NO_REDIRECT`; the host only persists and stays in the form |
| Return | Promise, always resolves (enables chaining: persist → render ending) |
| Don't use for | driving the ending display — first show the in-form DOM, then call this interface to persist |

**Recommended call** (in the `survey-ui.js` LLM custom interaction area):

```javascript
async function showEndingAndPersist() {
  // 1. switch to the in-form ending DOM (show/hide or page to the ending screen)
  await SurveyDataBridge.submitAndStay({
    answers: buildAnswers(),
  })
}
```

- If `answers` is omitted, the bridge auto-collects; free mode recommends passing `buildAnswers()` explicitly.
- Keep the `buildAnswers()` function; validators depend on it.
- **Forbidden**: persisting with `submitSurvey()` / `SurveyDataBridge.submit()` and then showing the ending (it jumps to the host completion page).

## Assessment result persistence (when there's scoring/result)

After computing, set a user-readable display string, then call `submitAndStay` (writes `t_survey_answer.eval_result`, shown on the statistics page):

```javascript
window.__WJ_EVAL_RESULT__ = '85'        // sum: pure number
// or
window.__WJ_EVAL_RESULT__ = 'Leader'    // dimension: type-name title
await SurveyDataBridge.submitAndStay({
  answers: buildAnswers(),
  evalResult: window.__WJ_EVAL_RESULT__,  // may also pass explicitly
})
```

- `__WJ_EVAL_RESULT__` is a **string** (not an object); when unset, the bridge tries a fallback read from the standard `#eval-result-*` DOM.
- Forms going through `assessment-pattern` + `generate_assessment.py` set it automatically; no hand-writing.
- Forms going through `exam-pattern` + `generate_exam.py` set it automatically; no hand-writing.

## Submit entry

- The skeleton has no visible submit button by default; you must build a visible trigger (e.g. "View results", "Done") whose handler goes through `showEndingAndPersist`. If another button in the form calls `submitSurvey()`, it may be hidden, but the visible trigger above must remain.
- With immersive pagination, `state.totalPages` (or equivalent logic) must cover through the last question; the trigger chain points to the in-form ending + `submitAndStay`, not `submitSurvey()`.

## Ending DOM placement

In-form ending/poster HTML goes outside the question area — see **F5** (after `QUESTION_INSERT_POINT` or before `QUESTION_LIST_START`); don't place it in the question area where `generate_free_mode_skeleton.py --force` / append scripts would wipe it.

## Maintaining existing forms

After appending/deleting/reordering questions, if the form already uses this mode: confirm `buildAnswers()` is still complete, and the last page's trigger chain and `state.totalPages` (if any) still point to the in-form ending + `submitAndStay`.
