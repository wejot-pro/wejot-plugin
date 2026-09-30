## PMF answer-side requirements

- answerKeys example: `["disappointment_level"]`, values use the option copy in the survey's language.
- Use the custom question type GENERIC; standard question types are forbidden
- The answer-side component references single-choice questions

## PMF statistics chart requirements

Import one JS component to render the full PMF dashboard (needle, score, rating, per-option share cards); **do not write any extra statistics or rendering code outside the component**.

```html
<script src="https://wejot-pro.oss-cn-shenzhen.aliyuncs.com/jscript/generic-chart/gauge.js"></script>
```

In `renderChart`, convert `userAnswers` to the following format then call; the component handles all rendering:

```js
// value: 1=very disappointed, 2=somewhat disappointed, 3=not disappointed
SurveyCharts.pmf('#chart-el', {
  responses: [
    { value: 1, count: 120 },
    { value: 2, count: 65 },
    { value: 3, count: 35 }
  ]
})
```
