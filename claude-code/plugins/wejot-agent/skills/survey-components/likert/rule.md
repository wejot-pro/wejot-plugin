## Likert scale answer-side requirements

- For ordinary rating questions, prefer the standard question type `SCALE`; for satisfaction/rating matrices where all rows share the same set of scale columns, prefer the standard question type `MATRIX_SCALE`.
- When the matrix rows come from an enumerable candidate set at creation time, still use `MATRIX_SCALE`: write the full `rows` catalog and `dynamicRows: true` in the spec, then use `setQuestionItems(..., { slot: "matrixRows" })` to activate only a subset of the catalog. Standard matrices must not generate rows outside the schema.
- When candidate identity cannot be fully enumerated at creation time, or arbitrary dynamic ordering/custom per-item structure is needed, use a typed GENERIC and save a stable itemKey, the currently displayed label, source, exposure, and the question-type value in the answer.
- Only use the custom question type GENERIC when per-row controls, scoring structure, or interactions cannot be expressed by a standard Likert question. The `answerKeys`, HTML, CSS, and chart requirements below constrain only this custom path.
- GENERIC answerKeys example: use each row's dimension title as the key, e.g. `["Appearance","Price"]`.
- The rating buttons under each row must align strictly vertically with the header columns
- If a scale value is specified, option buttons must be round numeric buttons
**Mandatory example**:
```css
 .matrix-table button{
    display: inline-block !important;
    …
  }
```
```html
<table class="matrix-table">
  <thead>
    <tr>
      <th></th>
      <th>Strongly disagree</th>
      <th>Disagree</th>
      <th>Neutral</th>
      <th>Agree</th>
      <th>Strongly agree</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Appearance</td>
      <td><button>1</button></td>
      <td><button>2</button></td>
      <td><button>3</button></td>
      <td><button>4</button></td>
      <td><button>5</button></td>
    </tr>
  </tbody>
</table>
```
- If no scale value is specified, use single or multiple choice for the option buttons
**Mandatory example**:
```html
<table class="matrix-table">
  <thead>
    <tr>
      <th></th>
      <th>Strongly disagree</th>
      <th>Disagree</th>
      <th>Neutral</th>
      <th>Agree</th>
      <th>Strongly agree</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Appearance</td>
      <td><input type="radio" /></td>
      <td><input type="radio" /></td>
      <td><input type="radio" /></td>
      <td><input type="radio" /></td>
      <td><input type="radio" /></td>
    </tr>
  </tbody>
</table>
```
- Except for the left-aligned scale question description text, all elements in cells must be centered

## Likert scale statistics chart requirements

### When the content in the Likert question defines a metric, consider displaying it with the gauge component:

### Import

```html
<script src="https://wejot-pro.oss-cn-shenzhen.aliyuncs.com/jscript/generic-chart/gauge.js"></script>
```

### Docs
https://wejot-pro.oss-cn-shenzhen.aliyuncs.com/jscript/generic-chart/gauge.md
