import "./LessonPlanPreview.css";

function planToMarkdown(topic, plan) {
  const lines = [`# מערך שיעור: ${topic}`, "", "## מטרות"];
  plan.goals.forEach((g) => lines.push(`- ${g}`));
  lines.push("", "## פעילויות");
  plan.activities.forEach((a, i) => {
    lines.push(`### ${i + 1}. ${a.title}`);
    if (a.summary) lines.push(a.summary);
    lines.push(`- חילופי דברים אוטונומיים: ${a.autonomous_exchanges}`);
    lines.push(`- שאלת בדיקה: ${a.checkpoint_question}`);
    lines.push("");
  });
  return lines.join("\n");
}

function downloadMarkdown(topic, plan) {
  const md = planToMarkdown(topic, plan);
  const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `מערך-שיעור-${topic}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

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
            <div className="activity-title">{i + 1}. {a.title}</div>
            {a.summary && <div className="activity-summary">{a.summary}</div>}
            <div className="activity-meta">
              {a.autonomous_exchanges > 0
                ? `${a.autonomous_exchanges} חילופי דברים בין התלמידים, ואז שאלת בדיקה`
                : "ישר לשאלת בדיקה"}
            </div>
          </div>
        ))}
      </div>

      <div className="plan-actions">
        <button className="btn btn-primary" onClick={onStart}>התחל לפי המערך</button>
        <button className="btn btn-ghost" onClick={onRegenerate} disabled={regenerating}>
          {regenerating ? "מייצר מחדש..." : "ייצר מחדש"}
        </button>
        <button className="btn btn-ghost" onClick={() => downloadMarkdown(topic, plan)}>ייצוא Markdown</button>
        <button className="btn btn-ghost" onClick={onCancel}>ביטול</button>
      </div>
    </div>
  );
}
