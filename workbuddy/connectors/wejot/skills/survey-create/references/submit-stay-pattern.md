# Persist answers and remain inside the survey

Use this pattern when the final screen is an in-survey thank-you page, result summary, poster, or another custom view and answers must be persisted without switching to the host's generic completion screen.

## Contract

Call `SurveyDataBridge.submitAndStay(options)`. It sends a no-redirect submission and returns a Promise that always resolves so the local ending flow can continue.

```javascript
async function showEndingAndPersist() {
  showEndingScreen()
  await SurveyDataBridge.submitAndStay({
    answers: buildAnswers()
  })
}
```

Render or reveal the ending first, then persist. Do not call `submitSurvey()` or `SurveyDataBridge.submit()` and then attempt to show the ending, because redirecting submission causes the host to hide the survey.

If the survey computes a result, provide one user-readable string:

```javascript
window.__WJ_EVAL_RESULT__ = '85'
await SurveyDataBridge.submitAndStay({
  answers: buildAnswers(),
  evalResult: window.__WJ_EVAL_RESULT__
})
```

Dimension assessments use the type title; score assessments use a numeric string. Generated assessment and exam flows set this automatically.

Keep `buildAnswers()` for validation. Add a visible trigger such as “View results” or “Finish,” and wire its handler to the ending plus `submitAndStay`. In paged experiences, include the final question in the page count and route its completion to this trigger.

Place ending DOM outside the generated question region, before `QUESTION_LIST_START` or after `QUESTION_INSERT_POINT`, so regeneration does not discard it.
