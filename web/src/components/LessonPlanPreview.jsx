import { stageLabel } from "../lib/lessonStages";
import { downloadLessonPlan } from "../lib/export/markdown";
import "./LessonPlanPreview.css";

export default function LessonPlanPreview({ topic, plan, onStart, onRegenerate, onCancel, regenerating }) {
  return (
    <div className="lesson-plan-preview">
      <h2>מערך השיעור</h2>
      <p className="subtitle">נושא: {topic}</p>

      <h4>מטרות</h4>
      <ul className="plan-goals">
        {plan.goals.map((g, i) => <li key={i}>{g}</li>)}
      </ul>

      <h4>פעילויות</h4>
      <div className="plan-activities">
        {plan.activities.map((a, i) => (
          <div className="plan-activity" key={i}>
            <div className="activity-title">
              {i + 1}. <span className="activity-stage">{stageLabel(a.stage)}</span> — {a.title}
            </div>
            {a.summary && <div className="activity-summary">{a.summary}</div>}
            <div className="activity-meta">
              {a.autonomous_exchanges > 0
                ? `${a.autonomous_exchanges} חילופי דברים בין התלמידים, ואז שאלת בדיקה`
                : "ישר לשאלת בדיקה"}
            </div>
          </div>
        ))}
      </div>

      {plan.homework && (
        <>
          <h4>שיעורי בית</h4>
          <p className="plan-homework">{plan.homework}</p>
        </>
      )}

      <div className="plan-actions">
        <button className="btn btn-primary" onClick={onStart}>התחל לפי המערך</button>
        <button className="btn btn-ghost" onClick={onRegenerate} disabled={regenerating}>
          {regenerating ? "מייצר מחדש..." : "ייצר מחדש"}
        </button>
        <button className="btn btn-ghost" onClick={() => downloadLessonPlan(topic, plan)}>ייצוא Markdown</button>
        <button className="btn btn-ghost" onClick={onCancel}>ביטול</button>
      </div>
    </div>
  );
}
