# SurveyCharts.datetime date/time picker

An independent JavaScript library built for the Tencent Survey date/time question type, supporting multiple date/time selection modes.

## Features

- ✅ **DatePicker** - date picker (year/month/day)
- ✅ **TimePicker** - time picker (hour/minute)
- ✅ **MonthPicker** - month picker (year/month)
- ✅ **WeekPicker** - week picker (select by week)
- ✅ **RangePicker** - date range picker (start-end dates)
- 🎨 Collapsed by default; popup opens on click
- 🎨 Popup has confirm/cancel buttons
- 🎨 Calendar style, five days per row
- 🎨 Supports year/month/week switching
- 📱 Responsive design, mobile-friendly
- 🎯 Zero dependencies, pure native JavaScript (CSS auto-injected inline)

## Installation

Import the JS file directly:

```html
<script src="datetime.js"></script>
```

## Usage

### DatePicker - date picker

```html
<div id="date-picker"></div>

<script>
var datePicker = SurveyCharts.datetime.date('#date-picker', {
  placeholder: 'Please select a date',
  value: '2026-04-02',  // optional, initial value
  onChange: function(value) {
    console.log('selected date:', value);  // format: YYYY-MM-DD
  }
});

// get value
var value = datePicker.getValue();

// set value
datePicker.setValue('2026-05-01');
</script>
```

### TimePicker - time picker

```html
<div id="time-picker"></div>

<script>
var timePicker = SurveyCharts.datetime.time('#time-picker', {
  placeholder: 'Please select a time',
  value: '14:30',  // optional, initial value
  onChange: function(value) {
    console.log('selected time:', value);  // format: HH:mm
  }
});
</script>
```

### MonthPicker - month picker

```html
<div id="month-picker"></div>

<script>
var monthPicker = SurveyCharts.datetime.month('#month-picker', {
  placeholder: 'Please select a month',
  value: '2026-04',  // optional, initial value
  onChange: function(value) {
    console.log('selected month:', value);  // format: YYYY-MM
  }
});
</script>
```

### WeekPicker - week picker

```html
<div id="week-picker"></div>

<script>
var weekPicker = SurveyCharts.datetime.week('#week-picker', {
  placeholder: 'Please select a week',
  onChange: function(value) {
    console.log('selected week:', value);  // format: YYYY-M-D (a day in that week)
  }
});
</script>
```

### RangePicker - date range picker

```html
<div id="range-picker"></div>

<script>
var rangePicker = SurveyCharts.datetime.range('#range-picker', {
  placeholder: 'Please select a date range',
  value: {  // optional, initial value
    start: '2026-04-01',
    end: '2026-04-15'
  },
  onChange: function(value) {
    console.log('selected range:', value);
    // value = { start: 'YYYY-MM-DD', end: 'YYYY-MM-DD' }
  }
});
</script>
```

## Configuration options

All pickers support these common options:

| Option | Type | Default | Description |
|------|------|--------|------|
| `placeholder` | String | `'Please select'` | Placeholder text when nothing is selected |
| `value` | String/Object | `null` | Initial value |
| `onChange` | Function | `null` | Callback when the value changes |
| `disabled` | Boolean | `false` | Whether disabled |

## API methods

All picker instances provide the following methods:

```javascript
// get the current value
var value = picker.getValue();

// set the value
picker.setValue(newValue);

// open the popup
picker.open();

// close the popup
picker.close();
```

## Style customization

CSS is auto-injected into `<head>` on first init. Override the standard class names to customize the look:

```css
/* custom theme color */
.dt-picker-btn-confirm {
  background: #your-color;
}

.dt-calendar-day-selected {
  background: #your-color !important;
}
```

Main CSS classes:

- `.dt-picker` - picker container
- `.dt-picker-input` - input
- `.dt-picker-popup` - popup
- `.dt-calendar-day` - calendar date
- `.dt-time-item` - time item
- `.dt-month-item` - month item

## Browser compatibility

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)
- Mobile browsers

## Examples

See the `index.html` file for a full example.

## Design spec

- Rounded design (8px-16px)
- Flat style
- Theme color: #44435C
- Font: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC'
- Font weights: 400/500/600
- Responsive layout
