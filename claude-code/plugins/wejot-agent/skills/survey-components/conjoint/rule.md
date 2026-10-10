## Conjoint analysis requirements

- answerKeys example: per group `["Group 1"]`, values contain the selected combination's description in the survey's language.
- Conjoint must be a multi-group sequential question type (≥3 groups), combining every attribute; only 1 group shown per screen
- Bottom shows '<' , 'current group' / 'total groups' , '>'; first group doesn't show '<', last group doesn't show '>'; buttons and text on one line
- After each group is fully selected, auto-advance to the next group with a fade transition; card data is not lost
- The question counts as answered only when all groups are finished
