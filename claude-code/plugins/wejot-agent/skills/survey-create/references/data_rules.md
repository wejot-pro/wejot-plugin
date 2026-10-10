# Standard artifact data rules

Read `question_schema.json` before creating artifacts. Use `question_schema.example.json` only to understand structure; never copy its topic, copy, or UUIDs.

## Core invariants

- JSON must match the schema exactly. Do not invent root, question, or option fields such as `id`.
- Required survey fields are `survey.title` and `survey.description`.
- Every question requires `title`, `code`, `uuid`, `type`, `required`, and `sort`.
- Use a unique, meaningful, stable English `lower_snake_case` question `code`.
- Sort questions in increments of 1000.
- HTML `data-question-uuid` must equal JSON `uuid`.
- Write JSON first, then generate HTML from its identities and structure.
- Option labels are the visible text of `[data-option]`. Render selection decorations with CSS, not text nodes.

Supported type names and HTML numeric values are: `RADIO` 8, `CHECKBOX` 9, `TEXTAREA` 1 or 3, `SCALE` 10, `UPLOAD` 15, `MATRIX_SCALE` 28, and `GENERIC` 39.

## Standard question root

Each question root must include both `question-item` and `answer-question-item`, plus `data-question-uuid`, `data-question-type`, `data-question-index`, `data-required`, and `data-page`. It must contain a visible number element and the editor footer expected by the standard template. Use `survey-unified-sample.html` or `generate_standard_survey.py`; do not simplify the required structure.

```html
<div class="question-item answer-question-item"
     data-question-uuid="example-question-uuid"
     data-question-type="8"
     data-question-index="1"
     data-required="true"
     data-page="1">
  <div class="qn" data-q-number>01</div>
  <div data-title>Question title</div>
  <div class="edit-only question-footer">
    <button class="btn-outline add-question" type="button">Add question</button>
    <button class="btn-icon drag-handle question-drag-handle" title="Drag"></button>
    <button class="btn-icon delete-question" title="Delete"></button>
  </div>
</div>
```

## Type mapping

- `RADIO`: `[data-option]` maps to `options`; each option requires `label`, `sort`, and `description`, using `""` when no description exists.
- `CHECKBOX`: map options as above; map `data-min-choices` and `data-max-choices` to `minChoices` and `maxChoices`.
- `TEXTAREA`: map `placeholder`, `defaultValue`, `minLength`, and `maxLength`.
- `SCALE`: map `[data-scale-value]` to numeric `option.score`, visible title, and sort order.
- `MATRIX_SCALE`: map row labels and order to rows, and scale values, titles, and order to columns. HTML row labels must exactly match the schema row title.
- `GENERIC`: map `data-answer-keys` to `answerKeys`. Provide complete `genericStyle`, `genericHtml`, `genericScript`, `userAnswersSample`, and `chartHtml` according to the example contract.

## Upload questions

- `maxFileCount` is a positive per-question limit supported by the generator and runtime. Choose it from the question meaning; default to 1 when no bound is stated rather than inventing a multi-file requirement.
- `maxFileSize` is a positive per-question limit in KB. Default to 102400 KB (100MB) when the requirement does not specify another supported limit.
- JSON `fileTypes` uses lowercase extensions without dots. HTML `accept` uses dotted extensions.
- Omit `fileTypes` to allow all supported formats. Narrow it only when the requirement explicitly restricts formats.
- Supported extensions are `jpg`, `jpeg`, `png`, `gif`, `bmp`, `webp`, `svg`, `heic`, `tiff`, `pdf`, `doc`, `docx`, `xls`, `xlsx`, `csv`, `ppt`, `pptx`, `txt`, `rtf`, `md`, `zip`, `rar`, `7z`, `gz`, `tar`, `mp3`, `wav`, `m4a`, `aac`, `ogg`, `flac`, `mp4`, `mov`, `avi`, `mkv`, `webm`, `wmv`, and `flv`.

Core logic must use stable `data-*` identities, not visible labels or presentation classes. HTML and JSON UUID counts, types, ordering, option values, scale scores, and matrix rows must remain coherent.
