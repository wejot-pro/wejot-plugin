## Dynamic table requirements

- answerKeys example: `["members"]`, values are arrays of objects, inner keys use column-header names in the survey's language.
- Use `<table>` for layout
- Choose appropriate controls per cell, including but not limited to fill, dropdown select, cascading select, date/time, etc.
- Set control widths intelligently per user need, e.g. name ~150px, age ~90px, email ~240px
- When there are too many columns, mobile exceeds screen width; allow horizontal scrolling in that case `overflow:scroll`
- If respondents need to add rows themselves, add a button (white with gray border) in the last table row with merged cells, button width:100%. When the table has ≥2 rows of data, provide row deletion
