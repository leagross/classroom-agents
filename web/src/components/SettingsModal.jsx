import { useEffect, useState } from "react";
import { getStoredApiKey, setStoredApiKey, clearStoredApiKey } from "../lib/api";

export default function SettingsModal({ open, onClose, onKeyChange }) {
  const [input, setInput] = useState(getStoredApiKey());

  useEffect(() => {
    if (open) setInput(getStoredApiKey());
  }, [open]);

  if (!open) return null;

  function save() {
    const val = input.trim();
    if (val) setStoredApiKey(val);
    onKeyChange();
    onClose();
  }

  function clear() {
    clearStoredApiKey();
    setInput("");
    onKeyChange();
  }

  const hasKey = !!getStoredApiKey();

  return (
    <div className="modal-overlay open" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal settings-modal">
        <button className="modal-close" onClick={onClose}>✕</button>
        <h3>מפתח API אישי</h3>
        <p>
          כדי להשתמש בשירות, כל משתמש מזין את מפתח ה-Anthropic (Claude) <b>שלו עצמו</b>.
          השרת <b>לא שומר</b> שום מפתח — הוא נשמר רק בדפדפן שלך (localStorage) ונשלח לשרת רק
          בזמן הקריאה עצמה, לשימוש חד-פעמי בלבד.
        </p>
        <p>אפשר לקבל מפתח ב-<a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener">console.anthropic.com</a></p>
        <input type="password" placeholder="sk-ant-..." value={input} onChange={(e) => setInput(e.target.value)} />
        <div className="modal-row">
          <button className="btn btn-primary" onClick={save}>שמור</button>
          <button className="btn btn-ghost" onClick={clear}>מחק</button>
        </div>
        <span className={"key-status " + (hasKey ? "set" : "unset")}>
          {hasKey ? "✓ מפתח מוגדר. אפשר להתחיל שיעור." : "נדרש מפתח כדי להתחיל שיעור."}
        </span>
      </div>
    </div>
  );
}
