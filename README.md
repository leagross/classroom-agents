# כיתה של סוכנים

אפליקציית ווב קטנה: צ'אט לימוד עם כמה "דמויות" וירטואליות (מורה + 2 סוכנים מתחלפים + קאמיאו נדיר), לפי התכנון שגובש בשיחה.

## הרכב הסוכנים

- **המורה** — קבוע, מקור האמת. כל תשובה שלו עוברת שכבת אימות עובדתית שקטה (מודל זול/מהיר) לפני שהיא מוצגת; אם נמצאת טעות, המורה מתקן ומנסה שוב (עד 2 פעמים).
- **מאגר רוטציה** — דני (תלמיד טועה-לפעמים), המעמיק, השטוח, המקשר. בכל שיעור נבחרים 2 מתוך 4, לפי הנושא:
  - נושא טכני/מדויק (מתמטיקה, פיזיקה, קוד...) → המעמיק + השטוח.
  - נושא נרטיבי/מושגי (היסטוריה, ערכים, ספרות...) → דני + המקשר.
  - נושא אחר → נבחרים אקראית.
- **הבדחן** — קאמיאו, מצטרף רק מדי 3-4 סבבים.

כל סבב: המורה מגיב (מאומת), ואחד משני סוכני המאגר מגיב בתורו (רוטציה), ובסבבים נדירים גם הבדחן.

במסך ההתחלה ניתן לבחור ידנית אילו 2 "תלמידים" מתוך 4 משתתפים בשיעור (עם אווטאר צבעוני לכל דמות), או להשאיר ללא בחירה ולתת למערכת לבחור אוטומטית לפי הנושא.

## הפעלה מקומית

```bash
cd backend
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # חובה
uvicorn main:app --host 0.0.0.0 --port 8000
```

ואז לפתוח בדפדפן: `http://localhost:8000`

### משתני סביבה אופציונליים
- `CLASSROOM_MODEL` — מודל לדמויות (ברירת מחדל: `claude-sonnet-5-5`)
- `CLASSROOM_VERIFIER_MODEL` — מודל לשכבת האימות השקטה (ברירת מחדל: `claude-haiku-5-5`)

## מבנה הפרויקט
```
backend/
  agents.py        # הגדרות הדמויות (system prompts)
  orchestrator.py  # state machine: בחירת מאגר, אימות מורה, סדר תגובות
  main.py          # FastAPI, מגיש גם את ה-frontend
  slack_bot.py      # אינטגרציית Slack (אופציונלי)
frontend/
  index.html       # צ'אט ווניל JS
```

## מה עוד שווה להוסיף בהמשך
- שמירת שיחות ב-DB (כרגע הכל ב-memory, נמחק עם ריסטרט).
- לוגיקת רלוונטיות חכמה יותר לבחירת מי מהמאגר מגיב בכל סבב (כרגע רוטציה פשוטה).
- הגבלת אורך תשובות אגרסיבית יותר (post-processing) אם סוכן "נשבר" מהכללים.

## פריסה חינמית ל-Render

הפרויקט כולל `render.yaml` (Blueprint) בשורש, כך ש-Render מגדיר הכל אוטומטית.

1. היכנס ל-https://render.com והתחבר עם GitHub.
2. New → Blueprint → בחר את ה-repo `classroom-agents`.
3. Render יזהה את `render.yaml` ויציע ליצור שירות `classroom-agents` בתוכנית Free.
4. לפני ה-Deploy הסופי, הוסף את משתנה הסביבה `ANTHROPIC_API_KEY` (הוא מוגדר כ-`sync: false` ב-render.yaml כדי שלא יישמר בקוד — יש להזין אותו ידנית בממשק של Render).
5. אשר את ה-Deploy. בתוך כמה דקות תקבל כתובת ציבורית כמו `https://classroom-agents.onrender.com`.

הערה: בתוכנית החינמית השירות "נרדם" אחרי זמן ללא תנועה, והבקשה הראשונה אחרי שינה עלולה לקחת כ-30-60 שניות.

## אינטגרציית Slack (אופציונלי)

ניתן לדבר עם הכיתה גם מתוך ערוץ Slack, בנוסף (או במקום) לאתר. כל ערוץ/DM מנהל שיעור אחד בכל פעם; כל דמות מפרסמת הודעה נפרדת עם שם ואימוג'י משלה.

### יצירת Slack App
1. היכנס ל-https://api.slack.com/apps → **Create New App** → **From scratch**.
2. בחר שם (למשל "כיתה של סוכנים") ואת ה-workspace שלך.
3. **OAuth & Permissions** → תחת **Bot Token Scopes** הוסף: `chat:write`, `commands`, `channels:history` (ולערוצים פרטיים גם `groups:history`), ו-`im:history` אם תרצה גם ב-DM.
4. **Install App to Workspace**, ואז העתק את ה-**Bot User OAuth Token** (מתחיל ב-`xoxb-...`).
5. **Basic Information** → **App Credentials** → העתק את ה-**Signing Secret**.
6. **Slash Commands** → **Create New Command**:
   - Command: `/classroom`
   - Request URL: `https://<הכתובת-שלך-ב-Render>/slack/commands`
   - Description: "התחל שיעור חדש"
7. **Event Subscriptions** → הפעל (Enable Events):
   - Request URL: `https://<הכתובת-שלך-ב-Render>/slack/events` (Slack ישלח אימות אוטומטי — ה-endpoint כבר תומך בזה).
   - תחת **Subscribe to bot events** הוסף: `message.channels` (ולפי הצורך גם `message.groups`, `message.im`, `app_mention`).
8. הוסף את הבוט לערוץ הרצוי (`/invite @שם-הבוט`).

### משתני סביבה נדרשים
- `SLACK_BOT_TOKEN` — ה-`xoxb-...` משלב 4.
- `SLACK_SIGNING_SECRET` — משלב 5.

מוגדרים ב-`render.yaml` עם `sync: false`, כך שצריך להזין אותם ידנית בממשק Render (Environment).

### שימוש
- `/classroom <נושא>` בערוץ — מתחיל שיעור חדש (בוחר אוטומטית הרכב מאגר לפי הנושא).
- כל הודעה רגילה בערוץ לאחר מכן נחשבת כשאלה/תשובה של המשתמש, וכל דמות עונה בהודעה נפרדת.
