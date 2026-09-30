## Region answer-side requirements

**Applicable scenario**: use when users need to select Chinese administrative divisions (province / city / district) or fill in a detailed address. Supports four modes: cascade selection, single, multiple, and address input.

**Forbidden**: calling WebSearch/WebFetch to query province/city/district data, or hardcoding any city array.
**Already available**: the component `SurveyComponents.region` has the complete Chinese administrative-division data built in (34 provinces / 333 cities / 2800+ districts), call it directly; no external data preparation needed.

- Use the custom question type GENERIC
- Only create an empty container div; the component renders the full UI automatically and submits the answer automatically

### Full example

genericHtml (container):

```html
<div id="region-picker"></div>
```

genericScript (bare code fragment, **don't wrap in IIFE**; `questionId` is injected by the base, use it directly, **don't redefine or hardcode it**):

```javascript
SurveyComponents.load('region', function() {
  SurveyComponents.region('#region-picker', {
    questionId: questionId,    // use the questionId injected by the base (question UUID); the component submits automatically based on it
    level: 3,                  // 1=province, 2=province+city, 3=province+city+district
    mode: 'cascade',           // cascade|single|multiple|address
    border: '#F8F8FC',         // border color (optional)
    background: '#ffffff',     // background color (optional)
    activeBorder: '#838390'    // active border (optional)
  });
});
```

> ⚠️ Don't write `var questionId = 'xxx'`: the base has already injected the correct question UUID. Hardcoding (especially mistakenly using the question code) causes answers to be stored under the wrong key and lost on submission.

### Answer format

All modes uniformly return `{selections: [{item, category}]}`:
- `item`: the option display name or the detailed address (address mode)
- `category`: the full path (e.g. "Guangdong Province / Shenzhen City / Nanshan District")

**data-answer-keys**: `selections`

> Note: the component calls `submitGenericAnswer` automatically based on user actions; `data-answer-keys` is only used for backend format validation.

### Key constraints

1. **`questionId` must be passed**, and the component handles answer submission internally
2. **No need to hand-write `onChange` and `submitGenericAnswer`**
3. To read the current value, get the instance via the DOM:
   ```javascript
   var picker = document.querySelector('#region-picker')._surveyComponent;
   var val = picker.getValue();  // {value: {selections: [...]}, touched: boolean}
   ```
4. **Required validation checks `touched`**, not `selections.length`
