import { useEffect, useState } from "react";
import { getAgents } from "../lib/api";
import "./SetupForm.css";

export default function SetupForm({ hasApiKey, onOpenSettings, onStart }) {
  const [pool, setPool] = useState([]);
  const [topic, setTopic] = useState("");
  const [selected, setSelected] = useState([]);

  useEffect(() => {
    getAgents().then((data) => setPool(data.pool));
  }, []);

  function toggleAgent(key) {
    setSelected((prev) => {
      if (prev.includes(key)) return prev.filter((k) => k !== key);
      if (prev.length >= 2) return prev;
      return [...prev, key];
    });
  }

  function initials(name) {
    return name.replace(/^ה/, "").slice(0, 2);
  }

  function handleStart() {
    if (!hasApiKey) { onOpenSettings(); return; }
    if (!topic.trim()) return;
    onStart(topic.trim(), selected.length === 2 ? selected : null);
  }

  return (
    <div className="setup">
      <h2>שיעור חדש</h2>
      <p className="subtitle">חוג לימוד פרטי עם מספר מורים וירטואליים</p>
      <p>איזה נושא תרצה ללמוד היום?</p>
      <input
        placeholder="למשל: אלגברה לינארית, מלחמת העולם הראשונה, פוטוסינתזה..."
        value={topic}
        onChange={(e) => setTopic(e.target.value)}
      />

      <p className="hint">בחר ידנית 2 "תלמידים" שישתתפו בשיעור, או השאר לא-בחור ותן למערכת לבחור אוטומטית לפי הנושא:</p>
      <div className="pool-choices">
        {pool.map((agent) => {
          const isSelected = selected.includes(agent.key);
          const disabled = selected.length >= 2 && !isSelected;
          return (
            <div
              key={agent.key}
              className={"pool-card" + (isSelected ? " selected" : "") + (disabled ? " disabled" : "")}
              onClick={() => !disabled && toggleAgent(agent.key)}
            >
              <div className="avatar" style={{ background: agent.color }}>{initials(agent.name)}</div>
              <span>{agent.name}</span>
            </div>
          );
        })}
      </div>

      <button id="startBtn" className="btn btn-primary" disabled={!hasApiKey} onClick={handleStart}>
        התחל שיעור
      </button>
    </div>
  );
}
