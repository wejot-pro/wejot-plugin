## NPS answer-side requirements

- Use the custom question type GENERIC; standard question types are forbidden
- The UI must clearly show both endpoint anchor texts (e.g. "Not at all likely" ~ "Extremely likely")
- Buttons (perfect circles) evenly distributed across the page, aligned on both sides (mobile must also follow)
- On mobile, make option width/font as small as possible (recommended option width 20px, font 12px)

## Answer structure & submission (aligned with the survey-bridge.js data bridge)

- **The persistence key is fixed as `answer`** (integer 0–10). The inline-script element uses **`data-answer-keys="answer"`**, consistent with `GenericQuestionHandler` / `submitGenericAnswer` validation.
- Call **`window.submitGenericAnswer(questionId, { answer: <0..10> })`** to write the answer state; don't use ad-hoc field names like `score`, `rating`, `npsScore`, `value`.
- To fill the answer at the last moment before submission, listen to **`survey:before-submit`** then call `submitGenericAnswer`.
- **Read answers in business logic** via `SurveyDataBridge.getAnswer(questionUuid)?.value` (custom types and other question types uniformly use `.value`); **forbidden** to read NPS as single choice via **`optionValue`**.
- Difference from the chart below: the chart API uses **`scores[].score`** for "score bucket", which is a **report aggregation structure**; the submitted answer still uses **`answer`** — don't mix the key names.

## NPS statistics chart requirements

Import one JS component to render the full NPS dashboard (needle, score, rating, promoter/passive/detractor share cards); **do not write any extra statistics or rendering code outside the component**.

```html
<script src="https://wejot-pro.oss-cn-shenzhen.aliyuncs.com/jscript/generic-chart/gauge.js"></script>
```

In `renderChart`, convert `userAnswers` to the following format then call; the component handles all rendering:

```js
SurveyCharts.nps('#chart-el', {
  scores: [
    { score: 0, count: 3 },
    { score: 1, count: 2 },
    // ... score 0-10, count is the corresponding number of people
    { score: 10, count: 62 }
  ]
})
```
