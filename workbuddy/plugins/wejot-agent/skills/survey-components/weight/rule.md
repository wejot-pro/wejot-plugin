## Weight/ratio answer-side requirements

- Use the custom question type GENERIC
- Only create an empty container div; the component renders the full UI automatically and submits the answer automatically

### Full example

genericHtml (container):

```html
<div id="weight-picker"></div>
```

genericScript (bare code fragment, **don't wrap in IIFE**; `questionId` is injected by the base, use it directly, **don't redefine or hardcode it**):

```javascript
SurveyComponents.load('weight', function() {
  SurveyComponents.weight('#weight-picker', {
    questionId: questionId,    // use the questionId injected by the base (question UUID); the component submits automatically based on it
    items: [                   // options array (required)
      { key: 'Option A', label: 'A', value: 30 },
      { key: 'Option B', label: 'B', value: 70 }
    ],
    total: 100,                // total (optional, default 100)
    color: '#4A90D9',          // slider color (optional)
    border: '#F8F8FC',         // border color (optional)
    background: '#ffffff'      // background color (optional)
  });
});
```

> ⚠️ Don't write `var questionId = 'xxx'`: the base has already injected the correct question UUID. Hardcoding (especially mistakenly using the question code) causes answers to be stored under the wrong key and lost on submission.

### data-answer-keys

`Option A,Option B` (matching `items[].key`; use the survey's language, not a/b)

> Note: the component calls submitGenericAnswer automatically. The answer looks like `{"Option A": 30, "Option B": 70}`.

### Key constraints

1. **`questionId` must be passed**, and the component handles answer submission internally
2. **No need to hand-write `onChange` and `submitGenericAnswer`**
3. To read the current value, get the instance via the DOM:
   ```javascript
   var picker = document.querySelector('#weight-picker')._surveyComponent;
   var val = picker.getValue();  // {values: {...}, touched: boolean}
   ```
