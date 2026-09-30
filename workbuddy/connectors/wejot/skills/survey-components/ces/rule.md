## CES answer-side requirements

- answerKeys example: single row `["effort"]`; multi-row uses each row's dimension name as the key.
- Use the custom question type GENERIC; standard question types are forbidden
- The rating buttons under each row must align strictly vertically with the header columns
- Option buttons must be round numeric buttons
**Mandatory example**:
```css
 .ces-table button{
    display: inline-block !important;
    …
  }
```
```html
<table class="ces-table">
  <thead>
    <tr>
      <th></th>
      <th>Strongly disagree</th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th></th>
      <th>Strongly agree</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Convenience</td>
      <td><button>1</button></td>
      <td><button>2</button></td>
      <td><button>3</button></td>
      <td><button>4</button></td>
      <td><button>5</button></td>
      <td><button>6</button></td>
      <td><button>7</button></td>
    </tr>
  </tbody>
</table>
```
- Except for the left-aligned question description text, all elements in cells must be centered

## CES statistics chart requirements

Import one JS component to render the full CES dashboard (needle, score, rating, high/low effort share cards); **do not write any extra statistics or rendering code outside the component**.

```html
<script src="https://wejot-pro.oss-cn-shenzhen.aliyuncs.com/jscript/generic-chart/gauge.js"></script>
```

In `renderChart`, convert `userAnswers` to the following format then call; the component handles all rendering:

```js
SurveyCharts.ces('#chart-el', {
  responses: [
    { value: 1, count: 5 },
    { value: 2, count: 8 },
    // ... value is the rating (1-7), count is the corresponding number of people
    { value: 7, count: 30 }
  ]
})
```

The component auto-detects and adapts when the scale is not 7-point.
