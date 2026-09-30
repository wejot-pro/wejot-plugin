## CSAT answer-side requirements

- answerKeys example: single row `["satisfaction_rating"]`; multi-row uses each row's dimension name as the key.
- Use the custom question type GENERIC; standard question types are forbidden
- The rating buttons under each row must align strictly vertically with the header columns
- Option buttons must be round numeric buttons
**Mandatory example**:
```css
 .csat-table button{
    display: inline-block !important;
    …
  }
```
```html
<table class="csat-table">
  <thead>
    <tr>
      <th>Very dissatisfied</th>
      <th>Dissatisfied</th>
      <th>Neutral</th>
      <th>Satisfied</th>
      <th>Very satisfied</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><button>1</button></td>
      <td><button>2</button></td>
      <td><button>3</button></td>
      <td><button>4</button></td>
      <td><button>5</button></td>
    </tr>
  </tbody>
</table>
```

## CSAT statistics chart requirements

Import one JS component to render the full CSAT dashboard (needle, score, rating, satisfied/dissatisfied share cards); **do not write any extra statistics or rendering code outside the component**.

```html
<script src="https://wejot-pro.oss-cn-shenzhen.aliyuncs.com/jscript/generic-chart/gauge.js"></script>
```

In `renderChart`, convert `userAnswers` to the following format then call; the component handles all rendering:

```js
SurveyCharts.csat('#chart-el', {
  responses: [
    { value: 1, count: 8 },
    { value: 2, count: 12 },
    // ... value is the rating (1-5), count is the corresponding number of people
    { value: 5, count: 100 }
  ]
})
```

The component auto-detects and adapts when the scale is not 5-point.
