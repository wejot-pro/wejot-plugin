## Matrix fill requirements

- answerKeys example: `["RowName-ColumnName"]` or nested `{"RowName":{"ColumnName":"value"}}`.
- Use `<table> + <input type="text" />` for layout
- Choose appropriate controls per cell, including but not limited to fill, dropdown select, cascading select, date/time, etc.
- Set control widths intelligently per user need, e.g. name ~150px, age ~90px, email ~240px
- When there are too many columns, mobile exceeds screen width; allow horizontal scrolling in that case `overflow:scroll`
