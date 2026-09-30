## Ranking answer-side requirements

- answerKeys: static ranking can use `["ranking_result"]`; `UNBOUNDED_GENERIC` dynamic ranking MUST use `["items", "exposure"]`, submitting typed items — don't save only display copy or bare value arrays.
- Component library: sortablejs@1.15.2 is already loaded on the page; write drag scripts with sortablejs.
- UX: the drag hot zone is not limited to the handle; the whole row is draggable. placeholder size matches the option.
- Visuals: option sequence numbers use a gray background before sorting, and show the highlighted theme color only after sorting.
- **Forbidden** `transition` on `.sortable-item`; it breaks mobile dragging

```css
.sortable-item {
    /* transition: ;   must be empty! */
}
```

## Dynamic item adaptation

When the ranking question is a `GENERIC` target of `setQuestionItems`, `genericScript` only adapts this question and does not read any previous questions' answers. On init, first register the sync event, then `survey-ui.js` business logic computes the source and calls `setQuestionItems`:

```javascript
wrapper.addEventListener('survey:question-items', function(event) {
  var detail = event.detail || {}
  var items = Array.isArray(detail.items) ? detail.items : []
  var previousItems = detail.previousAnswer && Array.isArray(detail.previousAnswer.items)
    ? detail.previousAnswer.items
    : []
  var previousByKey = new Map(previousItems.map(function(item) {
    return [String(item.itemKey), item]
  }))
  var allowed = new Set(items.map(function(item) { return String(item.value) }))
  var orderedValues = previousItems
    .slice()
    .sort(function(a, b) {
      return Number(a.typeValue && a.typeValue.rank) - Number(b.typeValue && b.typeValue.rank)
    })
    .map(function(item) { return String(item.itemKey) })
    .filter(function(value) { return allowed.has(value) })
  items.forEach(function(item) {
    var value = String(item.value)
    if (orderedValues.indexOf(value) < 0) orderedValues.push(value)
  })

  renderRankingItems(items, orderedValues)
  var currentByKey = new Map(items.map(function(item) { return [String(item.value), item] }))
  var typedItems = orderedValues.map(function(itemKey, index) {
    var item = currentByKey.get(itemKey)
    var previous = previousByKey.get(itemKey)
    return {
      itemKey: itemKey,
      label: item.label,
      source: item.source || (previous && previous.source) || null,
      typeValue: { rank: index + 1 },
    }
  })
  detail.respond({ answer: { items: typedItems, exposure: detail.exposure } })
})
```

- `renderRankingItems` denotes the existing render function implemented inside this question's `genericScript`, not a base global; when generating a ranking question, implement it fully together with reading the post-drag order and re-rendering.
- `item.value` is written into `itemKey`, the stable primary key of the ranking answer; for fixed items, when display copy changes or the user edits "Other" text, keep position by the original itemKey.
- `item.label` is display copy; it must not be used as a dedupe, order-preservation, or answer primary key; when a source item is removed, delete the corresponding value from the answer; new items append at the end.
- `source` and Runtime `exposure` must enter the answer unchanged; `typeValue.rank` is the ranking question's type value. Charts aggregate by itemKey; label is display-only.
- `detail.respond({ answer: ... })` must execute synchronously in the event's current call stack. The handler must also update the component's internal order so later drags keep submitting the same `{ items, exposure }` typed contract.
- Empty items must render an empty state and respond with an empty array; don't keep the previous ranking.

## Ranking statistics chart requirements

- Use a table to list the overall rank of all options
- Use a chart to show the ranking distribution of all options
