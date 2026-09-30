## Date/time answer-side requirements

- Use the custom question type GENERIC
- Only create an empty container div; the component renders the full UI automatically and submits the answer automatically

### Full example

genericHtml (container):

```html
<div id="datetime-picker"></div>
```

genericScript (bare code fragment, **don't wrap in IIFE**; `questionId` is injected by the base, use it directly, **don't redefine or hardcode it**):

```javascript
SurveyComponents.load('datetime', function() {
  // supports date/time/month/week/datetime/range/timeRange
  SurveyComponents.datetime.date('#datetime-picker', {
    questionId: questionId,    // use the questionId injected by the base (question UUID); the component submits automatically based on it
    placeholder: 'Please select a date',
    border: '#F8F8FC',         // border color (optional)
    background: '#ffffff',     // background color (optional)
    activeBorder: '#838390',   // active border (optional)
    color: '#44435C'           // theme color (optional)
  });
});
```

> ⚠️ Don't write `var questionId = 'xxx'`: the base has already injected the correct question UUID. Hardcoding (especially mistakenly using the question code) causes answers to be stored under the wrong key and lost on submission.

### Answer format

`values` depends on the type:
- `date`:      `{value: 'YYYY-MM-DD'}`
- `time`:      `{value: 'HH:mm'}`
- `month`:     `{value: 'YYYY-MM'}`
- `week`:      `{value: 'YYYY-MM-DD'}`
- `datetime`:  `{value: 'YYYY-MM-DD HH:mm'}`
- `range`:     `{start: 'YYYY-MM-DD', end: 'YYYY-MM-DD'}`
- `timeRange`: `{start: 'HH:mm', end: 'HH:mm'}`

### Key constraints

1. **`questionId` must be passed**, and the component handles answer submission internally
2. **No need to hand-write `onChange` and `submitGenericAnswer`**
3. To read the current value, get the instance via the DOM:
   ```javascript
   var picker = document.querySelector('#datetime-picker')._surveyComponent;
   var val = picker.getValue();  // {values: {...}, touched: boolean}
   ```
4. **Required validation checks `touched`**
