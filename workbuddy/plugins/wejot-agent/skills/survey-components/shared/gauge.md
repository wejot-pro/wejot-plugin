# Generic gauge

When the NPS/CES/CSAT/PMF presets don't meet the need, customize with the generic gauge. The component renders everything by itself (gauge + legend + stat cards) in one call; don't write duplicate rendering code outside.

```html
<script src="https://wejot-pro.oss-cn-shenzhen.aliyuncs.com/jscript/generic-chart/gauge.js"></script>
```

### Full customization example

```html
<div id="chart"></div>
<script>
  var chart = SurveyCharts.gauge('#chart', {
    value: 82,
    min: 0,
    max: 100,
    zones: [
      { from: 0,  to: 25,  color: '#FB2C36', label: 'Poor' },
      { from: 25, to: 50,  color: '#EFC700', label: 'Fair' },
      { from: 50, to: 75,  color: '#5BB800', label: 'Good' },
      { from: 75, to: 100, color: '#00BC7D', label: 'Excellent' },
    ],
    ticks: [0, 25, 50, 75, 100],
    tooltip: [
      { color: '#00BC7D', text: 'Satisfied (80-100)' },
      { color: '#FB2C36', text: 'Unsatisfied (0-39)' },
      { color: null, text: 'Formula: Score = Satisfied / Total × 100' },
    ],
    legend: [
      { color: '#FB2C36', text: 'Unsatisfied' },
      { color: '#EFC700', text: 'Neutral' },
      { color: '#00BC7D', text: 'Satisfied' },
    ],
    stats: [
      { label: 'Unsatisfied', key: 'unsat', color: '#FB2C36' },
      { label: 'Score', key: 'score', color: null },
      { label: 'Satisfied', key: 'sat', color: '#00BC7D' },
    ],
    formatValue: function (v) { return Math.round(v) + '%' },
    onUpdate: function (v) {
      if (!chart) return;
      chart.updateStat('unsat', (100 - Math.round(v)) + '%');
      chart.updateStat('score', Math.round(v) + '%');
      chart.updateStat('sat', Math.round(v) + '%');
    },
  });
  chart.updateStat('unsat', '18%');
  chart.updateStat('score', '82%');
  chart.updateStat('sat', '82%');
</script>
```

### Configurable options

| Parameter | Description |
|------|------|
| `value, min, max` | Current value and range (default 0-100) |
| `zones` | Color zones `{from, to, color, label}` |
| `ticks` | Tick values array (default 4 equal parts) |
| `tooltip` | Question-mark hints `{color, text}`; color null means no color dot |
| `legend` | Legend `{color, text}` |
| `stats` | Bottom cards `{label, key, color}`, updated via `chart.updateStat(key, text)` |
| `formatValue` | Center value format function |
| `onUpdate` | Value-change callback (note: also fires on construction; add the `if (!chart) return` guard) |

Returns: `{ update(v), updateStat(key, text, color), destroy() }`
