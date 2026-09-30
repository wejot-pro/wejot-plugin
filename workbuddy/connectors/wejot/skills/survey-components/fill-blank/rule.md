## Fill-in-the-blank requirements

- answerKeys example: each fill label as the key, e.g. `["Name","Age"]`.
- Text and fills are mixed horizontally in groups; when wrapping, wrap at group boundaries
**Mandatory example**:
```css
@media (max-width: 768px) {
 .field-row {display: inline-block;width:auto;margin:0 10px 0;}
 .field-row label{display: inline-block;width:auto;}
 .field-row input{display: inline-block;width:auto;}
}
.field-row {display: inline-block;width:auto;}
 .field-row label{display: inline-block; width:auto;}
 .field-row input{display: inline-block;width:auto;}
```
```html
  <div class="field-row" >
    <label>Name:</label><input style="width:150px" />
  </div>
  <div class="field-row">
    <label>Age:</label><input style="width:90px" />
  </div>
  <div class="field-row">
    <label>Email:</label><input style="width:240px" />
  </div>
```
- Set fill widths intelligently per user need, e.g. name ~150px, age ~90px, email ~240px
- Choose input constraints intelligently per user need, including but not limited to character-count ranges, regex validation, digits-only / Chinese-only / English-only, etc.
- Choose the component presentation intelligently per user need, including but not limited to number, email, URL, password, etc.
- For short-answer fills, the field-row label + textarea occupies its own line at 100% width, with dynamic height expansion, character counting, and other interactions
- Provide clear error hints and localization: format errors, out-of-range, etc.
