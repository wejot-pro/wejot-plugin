## Signature answer-side requirements

- Use the custom question type GENERIC
- Only create an empty container div; the component renders the full UI automatically and submits the answer automatically

### Full example

genericHtml (container):

```html
<div id="signature-picker"></div>
```

genericScript (bare code fragment, **don't wrap in IIFE**; `questionId` is injected by the base, use it directly, **don't redefine or hardcode it**):

```javascript
SurveyComponents.load('signature', function() {
  SurveyComponents.signature('#signature-picker', {
    questionId: questionId,    // use the questionId injected by the base (question UUID); the component submits automatically based on it
    penColor: '#1f2937',       // pen color (optional)
    border: '#F8F8FC',         // border color (optional)
    background: '#ffffff',     // background color (optional)
    activeBorder: '#838390'    // active border (optional)
  });
});
```

> ⚠️ Don't write `var questionId = 'xxx'`: the base has already injected the correct question UUID. Hardcoding (especially mistakenly using the question code) causes answers to be stored under the wrong key and lost on submission.

### Answer format

The component submits `{signature: dataUrl}` automatically (empty signature is `{signature: ''}`).

**data-answer-keys**: `signature`

> Note: the component calls `submitGenericAnswer` automatically based on user actions; `data-answer-keys` is only used for backend format validation.

### Key constraints

1. **`questionId` must be passed**, and the component handles answer submission internally
2. **No need to hand-write `onChange` and `submitGenericAnswer`**
3. To read the current value, get the instance via the DOM:
   ```javascript
   var picker = document.querySelector('#signature-picker')._surveyComponent;
   var val = picker.getValue();  // {empty: boolean, touched: boolean, dataUrl: string}
   ```
4. **Required validation checks `touched`**
