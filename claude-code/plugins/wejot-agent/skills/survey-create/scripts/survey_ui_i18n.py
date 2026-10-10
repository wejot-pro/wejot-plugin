"""问卷回答端 UI 壳文案的语种注入。

survey-ui.js 跟随每份问卷在沙箱中生成，因此不在 JS 运行时内置全量字典，
而是由 generate_standard_survey.py / generate_free_mode_skeleton.py 接收
``--locale`` 参数，在写出 survey-ui.js 时只注入对应语种的文案。

语种解析：精确匹配 -> 主语言匹配 -> zh-* 回退 zh-CN，其它回退 en-US。
"""

from __future__ import annotations

import json
import re
import sys

DEFAULT_LOCALE = "zh-CN"
FALLBACK_NON_ZH = "en-US"

# key -> 模板。{n} / {m} / {min} / {max} / {count} / {optMax} 为前端运行时占位符；
# otherLabels 是“其它”选项标签的判定数组，注入后供 _isOtherSchemaLabel 使用。
SURVEY_UI_I18N = {
    "zh-CN": {
        "continue": "继续",
        "submit": "提交问卷",
        "minSelect": "第{n}题最少选{m}项",
        "maxSelect": "第{n}题最多选{m}项",
        "minInput": "第{n}题至少输入{m}字",
        "maxInput": "第{n}题最多输入{m}字",
        "completeQuestion": "请完成第{n}题",
        "completeMatrixRow": "请完成第{n}题（每行都需选择）",
        "completeAll": "请完成所有必填题",
        "uploadedFile": "已上传文件",
        "delete": "删除",
        "pagination": "分页",
        "option": "选项 {n}",
        "untitled": "无标题",
        "choicesExact": "需选 {min} 项（已选 {count}/{max}）",
        "choicesRange": "至少选 {min} 项，最多 {max} 项（已选 {count}/{optMax}）",
        "choicesAtLeast": "至少选 {min} 项（已选 {count}）",
        "choicesAtMost": "最多选 {max} 项（已选 {count}/{optMax}）",
        "otherLabels": ["其它", "其他"],
        "placeholder": "请输入...",
        "other": "其它",
        "upload": "上传",
        "clickToUpload": "点击上传",
        "pageBreak": "第 {n} 页",
        "startTest": "开始测试",
        "examTitle": "考试",
        "startExam": "开始考试",
        "nextQuestion": "下一题",
        "viewMyResult": "查看我的结果",
        "chooseOne": "选一个再继续哦~",
        "myResult": "我的结果",
        "totalScore": "综合得分",
        "poster": "生成海报",
        "share": "分享好友",
        "retry": "重新测一次",
        "examResultTitle": "考试结果",
        "submitted": "提交成功",
        "yourGrade": "您的档位",
        "fullScore": "满分",
        "completeQuestionFirst": "请先完成本题",
        "thanksDefault": "感谢您的作答，问卷已提交。",
        "scaleSatisfaction": ["非常不满意", "不满意", "一般", "满意", "非常满意"],
        "scaleMatrix": ["非常差", "一般", "非常好"],
        "examNoticeTotal": "共 {total} 题",
        "examNoticeScorable": "其中 {scorable} 题计入自动总分（文本题、上传题等不参与自动计分）",
        "examNoticeFullScore": "满分 {max} 分",
        "examNoticePassing": "{min} 分及以上为「{label}」",
        "passingLabel": "合格",
        "examNoticeRules": "按组合规则计分，请按题目要求作答",
        "examNoticeGradeResult": "提交后将按档位评定结果",
        "examNoticeScoreVisible": "提交后可查看成绩",
        "examNoticeCareful": "请认真作答后提交",
        "examNoticeThanksPage": "提交后将显示感谢页",
    },
    "zh-TW": {
        "continue": "繼續",
        "submit": "提交問卷",
        "minSelect": "第{n}題最少選{m}項",
        "maxSelect": "第{n}題最多選{m}項",
        "minInput": "第{n}題至少輸入{m}字",
        "maxInput": "第{n}題最多輸入{m}字",
        "completeQuestion": "請完成第{n}題",
        "completeMatrixRow": "請完成第{n}題（每行都需選擇）",
        "completeAll": "請完成所有必填題",
        "uploadedFile": "已上傳檔案",
        "delete": "刪除",
        "pagination": "分頁",
        "option": "選項 {n}",
        "untitled": "無標題",
        "choicesExact": "需選 {min} 項（已選 {count}/{max}）",
        "choicesRange": "至少選 {min} 項，最多 {max} 項（已選 {count}/{optMax}）",
        "choicesAtLeast": "至少選 {min} 項（已選 {count}）",
        "choicesAtMost": "最多選 {max} 項（已選 {count}/{optMax}）",
        "otherLabels": ["其他"],
        "placeholder": "請輸入...",
        "other": "其他",
        "upload": "上傳",
        "clickToUpload": "點擊上傳",
        "pageBreak": "第 {n} 頁",
        "startTest": "開始測試",
        "examTitle": "考試",
        "startExam": "開始考試",
        "nextQuestion": "下一題",
        "viewMyResult": "查看我的結果",
        "chooseOne": "請選擇一個選項再繼續",
        "myResult": "我的結果",
        "totalScore": "綜合得分",
        "poster": "生成海報",
        "share": "分享好友",
        "retry": "重新測一次",
        "examResultTitle": "考試結果",
        "submitted": "提交成功",
        "yourGrade": "您的檔位",
        "fullScore": "滿分",
        "completeQuestionFirst": "請先完成本題",
        "thanksDefault": "感謝您的作答，問卷已提交。",
        "scaleSatisfaction": ["非常不滿意", "不滿意", "一般", "滿意", "非常滿意"],
        "scaleMatrix": ["非常差", "一般", "非常好"],
        "examNoticeTotal": "共 {total} 題",
        "examNoticeScorable": "其中 {scorable} 題計入自動總分（文字題、上傳題等不參與自動計分）",
        "examNoticeFullScore": "滿分 {max} 分",
        "examNoticePassing": "{min} 分及以上為「{label}」",
        "passingLabel": "合格",
        "examNoticeRules": "依組合規則計分，請依題目要求作答",
        "examNoticeGradeResult": "提交後將依檔位評定結果",
        "examNoticeScoreVisible": "提交後可查看成績",
        "examNoticeCareful": "請仔細作答後提交",
        "examNoticeThanksPage": "提交後將顯示感謝頁",
    },
    "zh-HK": {
        "continue": "繼續",
        "submit": "提交問卷",
        "minSelect": "第{n}題最少選{m}項",
        "maxSelect": "第{n}題最多選{m}項",
        "minInput": "第{n}題至少輸入{m}字",
        "maxInput": "第{n}題最多輸入{m}字",
        "completeQuestion": "請完成第{n}題",
        "completeMatrixRow": "請完成第{n}題（每行都需選擇）",
        "completeAll": "請完成所有必填題",
        "uploadedFile": "已上傳檔案",
        "delete": "刪除",
        "pagination": "分頁",
        "option": "選項 {n}",
        "untitled": "無標題",
        "choicesExact": "需選 {min} 項（已選 {count}/{max}）",
        "choicesRange": "至少選 {min} 項，最多 {max} 項（已選 {count}/{optMax}）",
        "choicesAtLeast": "至少選 {min} 項（已選 {count}）",
        "choicesAtMost": "最多選 {max} 項（已選 {count}/{optMax}）",
        "otherLabels": ["其他"],
        "placeholder": "請輸入...",
        "other": "其他",
        "upload": "上傳",
        "clickToUpload": "點擊上傳",
        "pageBreak": "第 {n} 頁",
        "startTest": "開始測試",
        "examTitle": "考試",
        "startExam": "開始考試",
        "nextQuestion": "下一題",
        "viewMyResult": "查看我的結果",
        "chooseOne": "請揀一個選項再繼續",
        "myResult": "我的結果",
        "totalScore": "綜合得分",
        "poster": "生成海報",
        "share": "分享好友",
        "retry": "重新測一次",
        "examResultTitle": "考試結果",
        "submitted": "提交成功",
        "yourGrade": "您的檔位",
        "fullScore": "滿分",
        "completeQuestionFirst": "請先完成本題",
        "thanksDefault": "多謝你的作答，問卷已遞交。",
        "scaleSatisfaction": ["非常不滿意", "不滿意", "一般", "滿意", "非常滿意"],
        "scaleMatrix": ["非常差", "一般", "非常好"],
        "examNoticeTotal": "共 {total} 題",
        "examNoticeScorable": "其中 {scorable} 題計入自動總分（文字題、上載題等唔參與自動計分）",
        "examNoticeFullScore": "滿分 {max} 分",
        "examNoticePassing": "{min} 分或以上為「{label}」",
        "passingLabel": "合格",
        "examNoticeRules": "按組合規則計分，請按題目要求作答",
        "examNoticeGradeResult": "提交後會按檔位評定結果",
        "examNoticeScoreVisible": "提交後可以睇成績",
        "examNoticeCareful": "請認真作答先提交",
        "examNoticeThanksPage": "提交後會顯示感謝頁",
    },
    "en-US": {
        "continue": "Continue",
        "submit": "Submit",
        "minSelect": "Question {n}: select at least {m}",
        "maxSelect": "Question {n}: select at most {m}",
        "minInput": "Question {n}: enter at least {m} characters",
        "maxInput": "Question {n}: enter at most {m} characters",
        "completeQuestion": "Please complete question {n}",
        "completeMatrixRow": "Please complete question {n} (select every row)",
        "completeAll": "Please complete all required questions",
        "uploadedFile": "Uploaded file",
        "delete": "Delete",
        "pagination": "Page",
        "option": "Option {n}",
        "untitled": "Untitled",
        "choicesExact": "Select {min} (selected {count}/{max})",
        "choicesRange": "Select {min}-{max} (selected {count}/{optMax})",
        "choicesAtLeast": "Select at least {min} (selected {count})",
        "choicesAtMost": "Select at most {max} (selected {count}/{optMax})",
        "otherLabels": ["Other"],
        "placeholder": "Please enter...",
        "other": "Other",
        "upload": "Upload",
        "clickToUpload": "Click to upload",
        "pageBreak": "Page {n}",
        "startTest": "Start",
        "examTitle": "Exam",
        "startExam": "Start exam",
        "nextQuestion": "Next",
        "viewMyResult": "View my result",
        "chooseOne": "Please select an option to continue",
        "myResult": "My result",
        "totalScore": "Total score",
        "poster": "Create poster",
        "share": "Share",
        "retry": "Retake",
        "examResultTitle": "Exam result",
        "submitted": "Submitted",
        "yourGrade": "Your grade",
        "fullScore": "Full score",
        "completeQuestionFirst": "Please complete this question",
        "thanksDefault": "Thank you for your answers. Your survey has been submitted.",
        "scaleSatisfaction": ["Very dissatisfied", "Dissatisfied", "Neutral", "Satisfied", "Very satisfied"],
        "scaleMatrix": ["Very poor", "Average", "Very good"],
        "examNoticeTotal": "Total: {total} questions",
        "examNoticeScorable": "{scorable} of these count toward your automatic score (text and upload questions do not)",
        "examNoticeFullScore": "Full score: {max} points",
        "examNoticePassing": "{min} points or more is '{label}'",
        "passingLabel": "Pass",
        "examNoticeRules": "Scored by combination rules; answer each question as instructed",
        "examNoticeGradeResult": "Your grade will be determined after submission",
        "examNoticeScoreVisible": "You can view your score after submitting",
        "examNoticeCareful": "Please answer carefully before submitting",
        "examNoticeThanksPage": "A thank-you page will be shown after submitting",
    },
    "es-MX": {
        "continue": "Continuar",
        "submit": "Enviar",
        "minSelect": "Pregunta {n}: seleccione al menos {m}",
        "maxSelect": "Pregunta {n}: seleccione como máximo {m}",
        "minInput": "Pregunta {n}: introduzca al menos {m} caracteres",
        "maxInput": "Pregunta {n}: introduzca como máximo {m} caracteres",
        "completeQuestion": "Complete la pregunta {n}",
        "completeMatrixRow": "Complete la pregunta {n} (seleccione cada fila)",
        "completeAll": "Complete todas las preguntas obligatorias",
        "uploadedFile": "Archivo subido",
        "delete": "Eliminar",
        "pagination": "Página",
        "option": "Opción {n}",
        "untitled": "Sin título",
        "choicesExact": "Seleccione {min} (seleccionados {count}/{max})",
        "choicesRange": "Seleccione entre {min} y {max} (seleccionados {count}/{optMax})",
        "choicesAtLeast": "Seleccione al menos {min} (seleccionados {count})",
        "choicesAtMost": "Seleccione como máximo {max} (seleccionados {count}/{optMax})",
        "otherLabels": ["Otro"],
        "placeholder": "Introduzca...",
        "other": "Otro",
        "upload": "Subir",
        "clickToUpload": "Haz clic para subir",
        "pageBreak": "Página {n}",
        "startTest": "Comenzar",
        "examTitle": "Examen",
        "startExam": "Comenzar examen",
        "nextQuestion": "Siguiente",
        "viewMyResult": "Ver mi resultado",
        "chooseOne": "Selecciona una opción para continuar",
        "myResult": "Mi resultado",
        "totalScore": "Puntuación total",
        "poster": "Crear póster",
        "share": "Compartir",
        "retry": "Repetir",
        "examResultTitle": "Resultado del examen",
        "submitted": "Enviado",
        "yourGrade": "Tu calificación",
        "fullScore": "Puntuación máxima",
        "completeQuestionFirst": "Complete esta pregunta",
        "thanksDefault": "Gracias por sus respuestas. Su encuesta ha sido enviada.",
        "scaleSatisfaction": ["Muy insatisfecho", "Insatisfecho", "Neutral", "Satisfecho", "Muy satisfecho"],
        "scaleMatrix": ["Muy malo", "Regular", "Muy bueno"],
        "examNoticeTotal": "Total: {total} preguntas",
        "examNoticeScorable": "{scorable} de ellas cuentan para su puntuación automática (las preguntas de texto y archivos no)",
        "examNoticeFullScore": "Puntuación máxima: {max} puntos",
        "examNoticePassing": "{min} puntos o más es '{label}'",
        "passingLabel": "Aprobado",
        "examNoticeRules": "Se puntúa según reglas combinadas; responda según las instrucciones",
        "examNoticeGradeResult": "Su calificación se determinará después del envío",
        "examNoticeScoreVisible": "Puede ver su puntuación después de enviar",
        "examNoticeCareful": "Responda con cuidado antes de enviar",
        "examNoticeThanksPage": "Se mostrará una página de agradecimiento después de enviar",
    },
    "ja-JP": {
        "continue": "続ける",
        "submit": "送信",
        "minSelect": "質問{n}：{m}つ以上選択してください",
        "maxSelect": "質問{n}：{m}つ以下選択してください",
        "minInput": "質問{n}：{m}文字以上入力してください",
        "maxInput": "質問{n}：{m}文字以下入力してください",
        "completeQuestion": "質問{n}を完了してください",
        "completeMatrixRow": "質問{n}を完了してください（各行を選択）",
        "completeAll": "すべての必須質問を完了してください",
        "uploadedFile": "アップロード済みファイル",
        "delete": "削除",
        "pagination": "ページ",
        "option": "選択肢 {n}",
        "untitled": "無題",
        "choicesExact": "{min}つ選択（選択済み {count}/{max}）",
        "choicesRange": "{min}〜{max}つ選択（選択済み {count}/{optMax}）",
        "choicesAtLeast": "{min}つ以上選択（選択済み {count}）",
        "choicesAtMost": "{max}つ以下選択（選択済み {count}/{optMax}）",
        "otherLabels": ["その他"],
        "placeholder": "入力してください",
        "other": "その他",
        "upload": "アップロード",
        "clickToUpload": "クリックしてアップロード",
        "pageBreak": "{n} ページ",
        "startTest": "テストを開始",
        "examTitle": "試験",
        "startExam": "試験を開始",
        "nextQuestion": "次の問題",
        "viewMyResult": "結果を見る",
        "chooseOne": "選択してください",
        "myResult": "私の結果",
        "totalScore": "総合スコア",
        "poster": "ポスター作成",
        "share": "シェア",
        "retry": "もう一度テスト",
        "examResultTitle": "試験結果",
        "submitted": "送信完了",
        "yourGrade": "あなたの評価",
        "fullScore": "満点",
        "completeQuestionFirst": "この質問を完了してください",
        "thanksDefault": "ご回答ありがとうございます。送信しました。",
        "scaleSatisfaction": ["とても不満", "不満", "普通", "満足", "とても満足"],
        "scaleMatrix": ["非常に悪い", "普通", "非常に良い"],
        "examNoticeTotal": "全{total}問",
        "examNoticeScorable": "うち{scorable}問が自動集計の対象です（テキスト・アップロード問題は対象外）",
        "examNoticeFullScore": "満点は{max}点です",
        "examNoticePassing": "{min}点以上で「{label}」です",
        "passingLabel": "合格",
        "examNoticeRules": "組み合わせルールで採点します。指示に従って回答してください",
        "examNoticeGradeResult": "送信後に評価が決定されます",
        "examNoticeScoreVisible": "送信後にスコアを確認できます",
        "examNoticeCareful": "回答してから送信してください",
        "examNoticeThanksPage": "送信後にお礼のページが表示されます",
    },
    "de-DE": {
        "continue": "Weiter",
        "submit": "Absenden",
        "minSelect": "Frage {n}: wählen Sie mindestens {m}",
        "maxSelect": "Frage {n}: wählen Sie höchstens {m}",
        "minInput": "Frage {n}: mindestens {m} Zeichen eingeben",
        "maxInput": "Frage {n}: höchstens {m} Zeichen eingeben",
        "completeQuestion": "Bitte beantworten Sie Frage {n}",
        "completeMatrixRow": "Bitte beantworten Sie Frage {n} (jede Zeile auswählen)",
        "completeAll": "Bitte beantworten Sie alle Pflichtfragen",
        "uploadedFile": "Datei hochgeladen",
        "delete": "Löschen",
        "pagination": "Seite",
        "option": "Option {n}",
        "untitled": "Ohne Titel",
        "choicesExact": "{min} auswählen (ausgewählt {count}/{max})",
        "choicesRange": "{min}–{max} auswählen (ausgewählt {count}/{optMax})",
        "choicesAtLeast": "Mindestens {min} auswählen (ausgewählt {count})",
        "choicesAtMost": "Höchstens {max} auswählen (ausgewählt {count}/{optMax})",
        "otherLabels": ["Sonstiges"],
        "placeholder": "Bitte eingeben...",
        "other": "Sonstiges",
        "upload": "Hochladen",
        "clickToUpload": "Zum Hochladen klicken",
        "pageBreak": "Seite {n}",
        "startTest": "Start",
        "examTitle": "Prüfung",
        "startExam": "Prüfung starten",
        "nextQuestion": "Weiter",
        "viewMyResult": "Mein Ergebnis ansehen",
        "chooseOne": "Bitte wählen Sie eine Option aus, um fortzufahren",
        "myResult": "Mein Ergebnis",
        "totalScore": "Gesamtpunktzahl",
        "poster": "Poster erstellen",
        "share": "Teilen",
        "retry": "Erneut testen",
        "examResultTitle": "Prüfungsergebnis",
        "submitted": "Übermittelt",
        "yourGrade": "Ihre Bewertung",
        "fullScore": "Volle Punktzahl",
        "completeQuestionFirst": "Bitte beantworten Sie diese Frage",
        "thanksDefault": "Vielen Dank für Ihre Antworten. Ihre Umfrage wurde übermittelt.",
        "scaleSatisfaction": ["Sehr unzufrieden", "Unzufrieden", "Neutral", "Zufrieden", "Sehr zufrieden"],
        "scaleMatrix": ["Sehr schlecht", "Durchschnittlich", "Sehr gut"],
        "examNoticeTotal": "Insgesamt {total} Fragen",
        "examNoticeScorable": "{scorable} davon fließen in die automatische Punktzahl ein (Text- und Upload-Fragen nicht)",
        "examNoticeFullScore": "Volle Punktzahl: {max}",
        "examNoticePassing": "{min} Punkte oder mehr ist '{label}'",
        "passingLabel": "Bestanden",
        "examNoticeRules": "Punktvergabe nach Kombinationsregeln; beantworten Sie jede Frage wie angegeben",
        "examNoticeGradeResult": "Ihre Bewertung wird nach der Übermittlung festgelegt",
        "examNoticeScoreVisible": "Sie können Ihr Ergebnis nach der Übermittlung einsehen",
        "examNoticeCareful": "Bitte beantworten Sie alles sorgfältig, bevor Sie absenden",
        "examNoticeThanksPage": "Nach der Übermittlung wird eine Dankesseite angezeigt",
    },
    "fr-FR": {
        "continue": "Continuer",
        "submit": "Envoyer",
        "minSelect": "Question {n} : sélectionnez au moins {m}",
        "maxSelect": "Question {n} : sélectionnez au plus {m}",
        "minInput": "Question {n} : saisissez au moins {m} caractères",
        "maxInput": "Question {n} : saisissez au plus {m} caractères",
        "completeQuestion": "Veuillez compléter la question {n}",
        "completeMatrixRow": "Veuillez compléter la question {n} (sélectionnez chaque ligne)",
        "completeAll": "Veuillez compléter toutes les questions obligatoires",
        "uploadedFile": "Fichier téléversé",
        "delete": "Supprimer",
        "pagination": "Page",
        "option": "Option {n}",
        "untitled": "Sans titre",
        "choicesExact": "Sélectionnez {min} (sélectionnés {count}/{max})",
        "choicesRange": "Sélectionnez {min}-{max} (sélectionnés {count}/{optMax})",
        "choicesAtLeast": "Sélectionnez au moins {min} (sélectionnés {count})",
        "choicesAtMost": "Sélectionnez au plus {max} (sélectionnés {count}/{optMax})",
        "otherLabels": ["Autre"],
        "placeholder": "Veuillez saisir...",
        "other": "Autre",
        "upload": "Téléverser",
        "clickToUpload": "Cliquez pour téléverser",
        "pageBreak": "Page {n}",
        "startTest": "Commencer",
        "examTitle": "Examen",
        "startExam": "Commencer l'examen",
        "nextQuestion": "Suivant",
        "viewMyResult": "Voir mon résultat",
        "chooseOne": "Veuillez sélectionner une option pour continuer",
        "myResult": "Mon résultat",
        "totalScore": "Score total",
        "poster": "Créer une affiche",
        "share": "Partager",
        "retry": "Refaire le test",
        "examResultTitle": "Résultat de l'examen",
        "submitted": "Envoyé",
        "yourGrade": "Votre note",
        "fullScore": "Note maximale",
        "completeQuestionFirst": "Veuillez compléter cette question",
        "thanksDefault": "Merci pour vos réponses. Votre questionnaire a été envoyé.",
        "scaleSatisfaction": ["Très insatisfait", "Insatisfait", "Neutre", "Satisfait", "Très satisfait"],
        "scaleMatrix": ["Très mauvais", "Moyen", "Très bon"],
        "examNoticeTotal": "Total : {total} questions",
        "examNoticeScorable": "{scorable} d'entre elles comptent dans votre score automatique (les questions de texte et de fichier non)",
        "examNoticeFullScore": "Note maximale : {max} points",
        "examNoticePassing": "{min} points ou plus correspond à « {label} »",
        "passingLabel": "Réussi",
        "examNoticeRules": "Noté selon des règles combinées ; répondez comme indiqué",
        "examNoticeGradeResult": "Votre note sera déterminée après l'envoi",
        "examNoticeScoreVisible": "Vous pouvez consulter votre score après l'envoi",
        "examNoticeCareful": "Veuillez répondre attentivement avant d'envoyer",
        "examNoticeThanksPage": "Une page de remerciement s'affichera après l'envoi",
    },
    "id-ID": {
        "continue": "Lanjut",
        "submit": "Kirim",
        "minSelect": "Pertanyaan {n}: pilih minimal {m}",
        "maxSelect": "Pertanyaan {n}: pilih maksimal {m}",
        "minInput": "Pertanyaan {n}: masukkan minimal {m} karakter",
        "maxInput": "Pertanyaan {n}: masukkan maksimal {m} karakter",
        "completeQuestion": "Selesaikan pertanyaan {n}",
        "completeMatrixRow": "Selesaikan pertanyaan {n} (pilih setiap baris)",
        "completeAll": "Selesaikan semua pertanyaan wajib",
        "uploadedFile": "File terunggah",
        "delete": "Hapus",
        "pagination": "Halaman",
        "option": "Opsi {n}",
        "untitled": "Tanpa judul",
        "choicesExact": "Pilih {min} (dipilih {count}/{max})",
        "choicesRange": "Pilih {min}-{max} (dipilih {count}/{optMax})",
        "choicesAtLeast": "Pilih minimal {min} (dipilih {count})",
        "choicesAtMost": "Pilih maksimal {max} (dipilih {count}/{optMax})",
        "otherLabels": ["Lainnya"],
        "placeholder": "Silakan masukkan...",
        "other": "Lainnya",
        "upload": "Unggah",
        "clickToUpload": "Klik untuk mengunggah",
        "pageBreak": "Halaman {n}",
        "startTest": "Mulai",
        "examTitle": "Ujian",
        "startExam": "Mulai ujian",
        "nextQuestion": "Berikutnya",
        "viewMyResult": "Lihat hasil saya",
        "chooseOne": "Silakan pilih satu opsi untuk melanjutkan",
        "myResult": "Hasil saya",
        "totalScore": "Skor total",
        "poster": "Buat poster",
        "share": "Bagikan",
        "retry": "Ulangi tes",
        "examResultTitle": "Hasil ujian",
        "submitted": "Terkirim",
        "yourGrade": "Nilai Anda",
        "fullScore": "Skor penuh",
        "completeQuestionFirst": "Selesaikan pertanyaan ini",
        "thanksDefault": "Terima kasih atas jawaban Anda. Kuesioner Anda telah dikirim.",
        "scaleSatisfaction": ["Sangat tidak puas", "Tidak puas", "Netral", "Puas", "Sangat puas"],
        "scaleMatrix": ["Sangat buruk", "Cukup", "Sangat baik"],
        "examNoticeTotal": "Total: {total} pertanyaan",
        "examNoticeScorable": "{scorable} di antaranya dihitung ke skor otomatis Anda (pertanyaan teks dan unggahan tidak)",
        "examNoticeFullScore": "Skor penuh: {max} poin",
        "examNoticePassing": "{min} poin atau lebih adalah '{label}'",
        "passingLabel": "Lulus",
        "examNoticeRules": "Dinilai berdasarkan aturan kombinasi; jawab sesuai instruksi",
        "examNoticeGradeResult": "Nilai Anda akan ditentukan setelah pengiriman",
        "examNoticeScoreVisible": "Anda dapat melihat skor setelah mengirim",
        "examNoticeCareful": "Harap jawab dengan cermat sebelum mengirim",
        "examNoticeThanksPage": "Halaman terima kasih akan ditampilkan setelah pengiriman",
    },
    "pt-BR": {
        "continue": "Continuar",
        "submit": "Enviar",
        "minSelect": "Pergunta {n}: selecione pelo menos {m}",
        "maxSelect": "Pergunta {n}: selecione no máximo {m}",
        "minInput": "Pergunta {n}: insira pelo menos {m} caracteres",
        "maxInput": "Pergunta {n}: insira no máximo {m} caracteres",
        "completeQuestion": "Conclua a pergunta {n}",
        "completeMatrixRow": "Conclua a pergunta {n} (selecione cada linha)",
        "completeAll": "Conclua todas as perguntas obrigatórias",
        "uploadedFile": "Arquivo enviado",
        "delete": "Excluir",
        "pagination": "Página",
        "option": "Opção {n}",
        "untitled": "Sem título",
        "choicesExact": "Selecione {min} (selecionados {count}/{max})",
        "choicesRange": "Selecione {min}-{max} (selecionados {count}/{optMax})",
        "choicesAtLeast": "Selecione pelo menos {min} (selecionados {count})",
        "choicesAtMost": "Selecione no máximo {max} (selecionados {count}/{optMax})",
        "otherLabels": ["Outro"],
        "placeholder": "Digite...",
        "other": "Outro",
        "upload": "Enviar",
        "clickToUpload": "Clique para enviar",
        "pageBreak": "Página {n}",
        "startTest": "Começar",
        "examTitle": "Prova",
        "startExam": "Começar prova",
        "nextQuestion": "Próxima",
        "viewMyResult": "Ver meu resultado",
        "chooseOne": "Selecione uma opção para continuar",
        "myResult": "Meu resultado",
        "totalScore": "Pontuação total",
        "poster": "Criar pôster",
        "share": "Compartilhar",
        "retry": "Refazer teste",
        "examResultTitle": "Resultado da prova",
        "submitted": "Enviado",
        "yourGrade": "Sua nota",
        "fullScore": "Nota máxima",
        "completeQuestionFirst": "Conclua esta pergunta",
        "thanksDefault": "Obrigado pelas suas respostas. Seu questionário foi enviado.",
        "scaleSatisfaction": ["Muito insatisfeito", "Insatisfeito", "Neutro", "Satisfeito", "Muito satisfeito"],
        "scaleMatrix": ["Muito ruim", "Regular", "Muito bom"],
        "examNoticeTotal": "Total: {total} perguntas",
        "examNoticeScorable": "{scorable} delas contam para sua pontuação automática (perguntas de texto e arquivo não)",
        "examNoticeFullScore": "Nota máxima: {max} pontos",
        "examNoticePassing": "{min} pontos ou mais é '{label}'",
        "passingLabel": "Aprovado",
        "examNoticeRules": "Pontuado por regras de combinação; responda conforme as instruções",
        "examNoticeGradeResult": "Sua nota será definida após o envio",
        "examNoticeScoreVisible": "Você pode ver sua pontuação após enviar",
        "examNoticeCareful": "Responda com atenção antes de enviar",
        "examNoticeThanksPage": "Uma página de agradecimento será exibida após o envio",
    },
    "vi-VN": {
        "continue": "Tiếp tục",
        "submit": "Gửi",
        "minSelect": "Câu {n}: chọn ít nhất {m}",
        "maxSelect": "Câu {n}: chọn tối đa {m}",
        "minInput": "Câu {n}: nhập ít nhất {m} ký tự",
        "maxInput": "Câu {n}: nhập tối đa {m} ký tự",
        "completeQuestion": "Vui lòng hoàn thành câu {n}",
        "completeMatrixRow": "Vui lòng hoàn thành câu {n} (chọn từng hàng)",
        "completeAll": "Vui lòng hoàn thành tất cả câu bắt buộc",
        "uploadedFile": "Tệp đã tải lên",
        "delete": "Xóa",
        "pagination": "Trang",
        "option": "Lựa chọn {n}",
        "untitled": "Chưa có tiêu đề",
        "choicesExact": "Chọn {min} (đã chọn {count}/{max})",
        "choicesRange": "Chọn {min}-{max} (đã chọn {count}/{optMax})",
        "choicesAtLeast": "Chọn ít nhất {min} (đã chọn {count})",
        "choicesAtMost": "Chọn tối đa {max} (đã chọn {count}/{optMax})",
        "otherLabels": ["Khác"],
        "placeholder": "Vui lòng nhập...",
        "other": "Khác",
        "upload": "Tải lên",
        "clickToUpload": "Nhấp để tải lên",
        "pageBreak": "Trang {n}",
        "startTest": "Bắt đầu",
        "examTitle": "Bài kiểm tra",
        "startExam": "Bắt đầu bài kiểm tra",
        "nextQuestion": "Tiếp theo",
        "viewMyResult": "Xem kết quả của tôi",
        "chooseOne": "Vui lòng chọn một lựa chọn để tiếp tục",
        "myResult": "Kết quả của tôi",
        "totalScore": "Tổng điểm",
        "poster": "Tạo áp phích",
        "share": "Chia sẻ",
        "retry": "Làm lại bài kiểm tra",
        "examResultTitle": "Kết quả bài kiểm tra",
        "submitted": "Đã gửi",
        "yourGrade": "Xếp hạng của bạn",
        "fullScore": "Điểm tối đa",
        "completeQuestionFirst": "Vui lòng hoàn thành câu này",
        "thanksDefault": "Cảm ơn bạn đã trả lời. Bảng khảo sát của bạn đã được gửi.",
        "scaleSatisfaction": ["Rất không hài lòng", "Không hài lòng", "Trung lập", "Hài lòng", "Rất hài lòng"],
        "scaleMatrix": ["Rất kém", "Trung bình", "Rất tốt"],
        "examNoticeTotal": "Tổng: {total} câu hỏi",
        "examNoticeScorable": "{scorable} trong số này tính vào điểm tự động của bạn (câu văn bản và tải lên không tính)",
        "examNoticeFullScore": "Điểm tối đa: {max} điểm",
        "examNoticePassing": "{min} điểm trở lên là '{label}'",
        "passingLabel": "Đạt",
        "examNoticeRules": "Chấm theo quy tắc kết hợp; hãy trả lời theo hướng dẫn",
        "examNoticeGradeResult": "Xếp hạng của bạn sẽ được xác định sau khi gửi",
        "examNoticeScoreVisible": "Bạn có thể xem điểm sau khi gửi",
        "examNoticeCareful": "Vui lòng trả lời cẩn thận trước khi gửi",
        "examNoticeThanksPage": "Trang cảm ơn sẽ được hiển thị sau khi gửi",
    },
}

I18N_BEGIN = "/*__SURVEY_UI_I18N_BEGIN__*/"
I18N_END = "/*__SURVEY_UI_I18N_END__*/"

# 额外语种字典（agent 通过 --i18n-dict / register_locale_dict 临时注册，不入主字典）
_EXTRA_LOCALES: dict[str, dict] = {}


def register_locale_dict(locale: str, data: dict) -> None:
    """注册一个额外语种字典（可只提供部分 key，缺失回退主字典对应语种或 en-US）。"""
    _EXTRA_LOCALES[locale.strip().replace("_", "-")] = data


def load_locale_dict_file(path) -> None:
    """从 JSON 文件加载额外语种字典：{locale: {key: value}, ...}。"""
    from pathlib import Path

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("--i18n-dict 文件必须是 {locale: {key: value}} 对象")
    known_keys = set(SURVEY_UI_I18N[FALLBACK_NON_ZH])
    for loc, items in data.items():
        if not isinstance(items, dict):
            raise ValueError(f"--i18n-dict 的 {loc!r} 必须是 {key: value} 对象")
        unknown = [k for k in items if k not in known_keys]
        if unknown:
            print(
                f"[i18n-dict] 警告：{loc} 含未知 key {unknown}，已忽略；"
                "可用 key 见 references/i18n-dict.example.json",
                file=sys.stderr,
            )
        register_locale_dict(loc, {k: v for k, v in items.items() if k in known_keys})


def is_builtin_locale(locale: str | None) -> bool:
    """locale 是否命中主字典（含主语言匹配）；额外/未覆盖语种返回 False。"""
    if not locale:
        return True
    value = locale.strip().replace("_", "-")
    if value in SURVEY_UI_I18N:
        return True
    base = value.split("-")[0].lower()
    return any(key.split("-")[0].lower() == base for key in SURVEY_UI_I18N)


def warn_if_custom_locale_needed(locale: str | None, i18n_dict: str | None) -> None:
    """渐进披露：用了未内置语种且未传 --i18n-dict 时，stderr 提示自定义方式。"""
    if not locale or i18n_dict:
        return
    if is_builtin_locale(locale):
        return
    from pathlib import Path

    example = Path(__file__).resolve().parent.parent / "references" / "i18n-dict.example.json"
    print(
        f"提示：--locale {locale} 不在内置语种内，壳文案将回退 en-US。"
        "如需自定义该语种壳文案，请加 --i18n-dict {文件}（JSON 结构为 {locale: {key: value}}）；"
        f"key 清单与韩语示例见 {example}，说明见同目录 i18n-dict.md。",
        file=sys.stderr,
    )


def _merged_dict(locale: str | None) -> dict:
    """返回语种解析后的合并字典：主字典 + 额外语种覆盖（缺 key 回退主字典）。"""
    resolved = resolve_locale(locale)
    base = resolved.split("-")[0].lower()
    fallback_key = DEFAULT_LOCALE if base == "zh" else FALLBACK_NON_ZH
    merged = dict(SURVEY_UI_I18N.get(resolved, {}))
    merged.update(_EXTRA_LOCALES.get(resolved, {}))
    if fallback_key != resolved:
        for key, value in SURVEY_UI_I18N[fallback_key].items():
            merged.setdefault(key, value)
    return merged


def resolve_locale(locale: str | None) -> str:
    """解析语种；未知语种回退到最接近的已支持语种。"""
    value = (locale or DEFAULT_LOCALE).strip().replace("_", "-")
    if value in SURVEY_UI_I18N or value in _EXTRA_LOCALES:
        return value
    base = value.split("-")[0].lower()
    for key in list(SURVEY_UI_I18N) + list(_EXTRA_LOCALES):
        if key.split("-")[0].lower() == base:
            return key
    return DEFAULT_LOCALE if base == "zh" else FALLBACK_NON_ZH


def js_dict_for_locale(locale: str | None) -> dict:
    return _merged_dict(locale)


def html_dict_for_locale(locale: str | None) -> dict:
    """生成 HTML 侧壳文案（占位符/其它选项/上传/完成语/分页）的语种字典。"""
    return _merged_dict(locale)


def other_labels_for_locale(locale: str | None) -> list[str]:
    """该语种用于判定「其它」选项的标签集合。"""
    return _merged_dict(locale).get("otherLabels", ["其他"])


def localized_default_scale_options(locale: str | None, *, matrix: bool = False) -> list[dict] | None:
    """量表/矩阵量表默认刻度的语种化结果；zh-CN 返回 None（沿用模板默认，保持历史行为）。"""
    resolved = resolve_locale(locale)
    if resolved == DEFAULT_LOCALE:
        return None
    labels = _merged_dict(resolved)["scaleMatrix" if matrix else "scaleSatisfaction"]
    if matrix:
        return [
            {"sort": i + 1, "score": float(i + 1), "title": t, "columnTitle": t}
            for i, t in enumerate(labels)
        ]
    return [{"sort": i + 1, "score": float(i + 1), "title": t} for i, t in enumerate(labels)]


def format_message(template: str, **params) -> str:
    """按 {key} 占位符填充消息模板（与前端 _suiT 的替换规则一致）。"""
    for key, value in params.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def _js_sui_t() -> str:
    """返回前端读取 SURVEY_UI_I18N 的运行时函数 _suiT（用于自由模式注入）。"""
    return """function _suiT(key, params) {
  var dict = (typeof SURVEY_UI_I18N !== 'undefined' && SURVEY_UI_I18N) || {};
  var msg = dict[key] != null ? dict[key] : '';
  if (params) {
    Object.keys(params).forEach(function (k) {
      msg = String(msg).replace(new RegExp('\\\\{' + k + '\\\\}', 'g'), params[k]);
    });
  }
  return msg;
}
"""


def inject_survey_ui_i18n(js_content: str, locale: str | None) -> str:
    """替换 survey-ui.js 中 I18N_BEGIN~I18N_END 之间的字典为指定语种。"""
    payload = json.dumps(js_dict_for_locale(locale), ensure_ascii=False, indent=2)
    replacement = f"{I18N_BEGIN}\n  const SURVEY_UI_I18N = {payload}\n  {I18N_END}"
    new_content, count = re.subn(
        re.escape(I18N_BEGIN) + r".*?" + re.escape(I18N_END),
        replacement,
        js_content,
        count=1,
        flags=re.S,
    )
    if count == 0:
        raise ValueError("survey-ui.js 缺少 SURVEY_UI_I18N 注入标记")
    return new_content


def free_mode_i18n_prelude(locale: str | None) -> str:
    """自由模式：生成 survey-ui.js 顶部注入的单语种字典与 _suiT。"""
    payload = json.dumps(js_dict_for_locale(locale), ensure_ascii=False, indent=2)
    return f"var SURVEY_UI_I18N = {payload};\n{_js_sui_t()}\n"
