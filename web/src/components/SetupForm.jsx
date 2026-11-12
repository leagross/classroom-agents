import { useEffect, useState } from "react";
import { getAgents, generateLessonPlan } from "../lib/api";
import LessonPlanPreview from "./LessonPlanPreview";
import "./SetupForm.css";

export default function SetupForm({ hasApiKey, onOpenSettings, onStart }) {
  const [pool, setPool] = useState([]);
  const [topic, setTopic] = useState("");
  const [selected, setSelected] = useState([]);
  const [sessionType, setSessionType] = useState("lesson"); // "lesson" | "review"
  const [preview, setPreview] = useState(null); // { plan, poolKeys }
  const [loadingPlan, setLoadingPlan] = useState(false);
  const [error, setError] = useState("");

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

  async function handlePrimaryAction() {
    if (!hasApiKey) { onOpenSettings(); return; }
    if (!topic.trim()) return;

    if (sessionType === "review") {
      onStart(topic.trim(), selected.length === 2 ? selected : null, null);
      return;
    }

    await buildPreview();
  }

  async function buildPreview() {
    setError("");
    setLoadingPlan(true);
    try {
      const poolKeysArg = selected.length === 2 ? selected : null;
      const { plan, pool: resolvedPool } = await generateLessonPlan(topic.trim(), poolKeysArg);
      setPreview({ plan, poolKeys: resolvedPool.map((a) => a.key) });
    } catch (e) {
      setError(e.message || "לא הצלחתי לבנות מערך שיעור. נסה שוב.");
    } finally {
      setLoadingPlan(false);
    }
  }

  if (preview) {
    return (
      <LessonPlanPreview
        topic={topic.trim()}
        plan={preview.plan}
        regenerating={loadingPlan}
        onStart={() => onStart(topic.trim(), preview.poolKeys, preview.plan)}
        onRegenerate={buildPreview}
        onCancel={() => setPreview(null)}
      />
    );
  }

  return (
    <div className="setup">
      <h2>שיעור חדש</h2>
      <p className="subtitle">חוג לימוד פרטי עם מספר מורים וירטואליים</p>

      <div className="session-type-choice">
        <button
          type="button"
          className={"session-type-btn" + (sessionType === "lesson" ? " selected" : "")}
          onClick={() => setSessionType("lesson")}
        >
          <div className="session-type-title">שיעור חדש</div>
          <div className="session-type-desc">נבנה מערך שיעור (מטרות + פעילויות) לפני שמתחילים</div>
        </button>
        <button
          type="button"
          className={"session-type-btn" + (sessionType === "review" ? " selected" : "")}
          onClick={() => setSessionType("review")}
        >
          <div className="session-type-title">חזרה על חומר</div>
          <div className="session-type-desc">שיחה חופשית, בלי מערך מוכן מראש</div>
        </button>
      </div>

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

      {error && <p className="setup-error">{error}</p>}

      <button id="startBtn" className="btn btn-primary" disabled={!hasApiKey || loadingPlan} onClick={handlePrimaryAction}>
        {loadingPlan ? "בונה מערך שיעור..." : sessionType === "lesson" ? "הכן מערך שיעור" : "התחל שיעור"}
      </button>
    </div>
  );
}
