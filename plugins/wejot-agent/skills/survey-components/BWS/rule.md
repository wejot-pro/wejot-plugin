## BWS requirements

- answerKeys example: per group `["Group 1","Group 2"]`, values `{"most_liked":"…","least_liked":"…"}`.
- BWS must be a multi-group sequential question type (≥3 groups); only 1 group shown per screen
- Presentation is limited to a 3-column table: left column attributes, middle column most liked (Best), right column least liked (Worst)
- Middle/right columns: fixed column width + vertical center alignment; text or radio horizontally aligned within cells
- Bottom shows '<' , 'current group' / 'total groups' , '>'; first group doesn't show '<', last group doesn't show '>'; last group needs no 'Done' button; all buttons and text on one line
- After each group is fully selected, auto-advance to the next group with a fade transition; card data is not lost
- The question counts as answered only when all groups are finished
