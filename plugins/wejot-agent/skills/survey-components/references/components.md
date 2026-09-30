# Component Families

Read the section matching the requested interaction. These are domain rules, not a promise that every component runtime is enabled; authoritative validation decides whether an artifact is supported.

## Choice and measurement

- **NPS:** 0-10 scale with explicit labels at both ends. Persist one integer score; do not confuse it with aggregated reporting rows.
- **CSAT / CES / PMF:** use a standard scale when possible. A custom presentation must keep ordered score values and visible labels aligned.
- **Likert:** prefer standard `SCALE` for one statement and `MATRIX_SCALE` when rows share a scale. Use `GENERIC` only when per-row controls or scoring differ materially.
- **BWS / MaxDiff:** present repeated sets when required. Record best and worst independently, disallow choosing the same item for both, preserve each set's identity, and require completion of every set.
- **Conjoint:** preserve set, profile, attribute, and level identities. Show one set at a time when requested and retain choices during navigation.
- **Weight allocation:** use stable item keys and enforce the declared total. Keep displayed rounding consistent with submitted values.

## Structured entry

- **Fill blank:** derive semantic keys from field meaning; use suitable input types and explicit format or range errors.
- **Matrix fill:** represent row and column identity in every answer. Allow horizontal scrolling on narrow screens instead of shrinking controls beyond usability.
- **Dynamic table:** persist rows as objects keyed by stable column semantics. Adding or deleting rows must not silently re-key retained rows.
- **Date/time:** persist an unambiguous format and distinguish date, time, datetime, range, month, and week modes.
- **Dropdown / cascade / region:** preserve stable values and the displayed hierarchy or path. Search is appropriate for long lists. Do not hard-code external geographic datasets into generated artifacts.
- **Signature:** make consent and purpose clear. Persist only the public contract's signature value and support clearing it.

## Ordering and grouping

- **Ranking:** persist stable item keys and rank order, not labels alone. Keyboard operation must be possible when drag-and-drop is offered.
- **Classification:** persist stable item keys under stable category keys. Prevent silent duplication or loss when moving items.
- **Dynamic candidates:** preserve source keys and actual exposure. If the full catalog is known, prefer a standard type with an activated subset; use `GENERIC` only for an unbounded candidate set or custom answer structure.

## Shared checks

- Declare exact answer keys and value types.
- Keep every label associated with its control and expose validation errors accessibly.
- Preserve state across pagination and rerendering.
- Test empty, minimum, maximum, invalid, and repeated-edit states.
- Do not assume a bundled third-party library or remote asset unless the public artifact contract explicitly guarantees it.
