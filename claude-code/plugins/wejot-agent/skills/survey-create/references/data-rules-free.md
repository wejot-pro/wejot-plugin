# Free-mode editing constraints

`generate_free_mode_skeleton.py` creates the bridge link, identity attributes, answer state, event bindings, and submission functions. After generation, customize presentation and interaction without breaking those contracts.

## Preserve these attributes

| Attribute | Purpose |
|---|---|
| `data-survey-role="survey"` | Survey root |
| `.pb[data-page-break="1"]` | Independent page boundary; one must precede the first question |
| `data-question` | Complete question wrapper |
| `data-q-number` | Visible question number |
| `data-title` | Question title without its number |
| `data-required` | Required state |
| `data-option` | One selectable option |
| `data-option-value` | Stable option value |
| `data-option-text` | Visible checkbox label inside its native `<label>` |
| `data-survey-role="scale-group"` | Scale container |
| `data-scale-value` | Scale score |
| `data-survey-role="matrix-group"` | Matrix container |
| `data-survey-role="matrix-row"` | Matrix row |
| `data-matrix-row` | Stable matrix-row identity |
| `data-matrix-row-label` | Matrix-row title |
| `data-survey-role="matrix-values"` | Matrix scale controls |
| `data-survey-role="generic-container"` | Custom question container |
| `data-survey-role="navigation"` | Navigation container |

Page-break nodes are direct children of the survey root and siblings of questions or question slides. Do not place `data-page-break` on a question, slide, option container, question-content container, or a container that holds question content. Question page numbers and page-break numbers must form the same set and appear in matching order.
| `data-nav-action` | Navigation action |
| `data-question-uuid` | Question identity injected by the builder |
| `data-min-choices`, `data-max-choices` | Checkbox bounds |
| `data-min-length`, `data-max-length` | Text bounds |
| `data-max-file-count`, `data-max-file-size` | Upload bounds |

Options must be individual selectable elements, not list containers. Render radio/check decorations with CSS so decoration text is not mistaken for the option label. Keep generated answer keys, UUIDs, `buildAnswers()`, and `submitSurvey()` coherent.

Write styles in `survey-ui.css` and interaction in the custom region of `survey-ui.js`. Existing legacy inline scripts remain valid, but do not modify the generated bootstrap casually.

Use `display: none` and explicit active states for paging. Keep navigation visible and above cards. A hidden file input must be wrapped by a clickable `<label>` or receive an explicit click-forwarding handler.

In JSON, upload `fileTypes` are lowercase extensions without dots, such as `["jpg","png","pdf"]`. HTML `accept` uses dotted values, such as `.jpg,.png,.pdf`.
