import { useState } from "react";
import { generateSyllabusLessonPlan } from "../lib/api/syllabus";
import { createSession, getSession } from "../lib/api/session";
import LessonPlanPreview from "./LessonPlanPreview";
import "./SyllabusList.css";

const STATUS_LABELS = {
  not_started: "לא התחיל",
  in_progress: "בתהליך",
  completed: "✓ הושלם",
};

/**
 * Shows a syllabus's lesson outline with each lesson's progress. Starting a
 * not_started lesson generates its full plan lazily (reusing the same
 * LessonPlanPreview approve/regenerate UI a standalone lesson uses) and only
 * then creates the actual session, tagged with this syllabus + lesson index.
 */
export default function SyllabusView({ syllabus, onBack, onSessionStart }) {
  const [current, setCurrent] = useState(syllabus);
  const [activeIndex, setActiveIndex] = useState(null);
  const [preview, setPreview] = useState(null); // { topic, plan, pool }
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function startLesson(index) {
    setError("");
    setLoading(true);
    setActiveIndex(index);
    try {
      const data = await generateSyllabusLessonPlan(current.id, index);
      setPreview(data);
    } catch (e) {
      setError(e.message || "לא הצלחתי לבנות מערך שיעור לשלב הזה.");
    } finally {
      setLoading(false);
    }
  }

  async function confirmStart() {
    try {
      const data = await createSession(preview.topic, preview.pool.map((a) => a.key), preview.plan, {
        syllabusId: current.id, lessonIndex: activeIndex,
      });
      onSessionStart(data, { syllabusId: current.id });
    } catch (e) {
      setError(e.message || "לא הצלחתי להתחיל את השיעור.");
    }
  }

  async function resumeLesson(sessionId) {
    try {
      const data = await getSession(sessionId);
      onSessionStart(data, { syllabusId: current.id });
    } catch (e) {
      setError(e.message || "לא הצלחתי לפתוח את השיעור הזה.");
    }
  }

  if (preview) {
    return (
      <LessonPlanPreview
        topic={preview.topic}
        plan={preview.plan}
        regenerating={loading}
        onStart={confirmStart}
        onRegenerate={() => startLesson(activeIndex)}
        onCancel={() => { setPreview(null); setActiveIndex(null); }}
        onTogglePresentation={(on) => setPreview((p) => ({ ...p, plan: { ...p.plan, presentation: on } }))}
      />
    );
  }

  return (
    <div className="syllabus-view">
      <button className="btn btn-ghost" onClick={onBack}>⟵ חזרה</button>
      <h2>סילבוס: {current.topic}</h2>

      <div className="syllabus-lessons">
        {current.lessons.map((l, i) => (
          <div className={"syllabus-lesson-row status-" + l.status} key={i}>
            <div className="syllabus-lesson-title">{i + 1}. {l.title}</div>
            {l.summary && <div className="syllabus-lesson-summary">{l.summary}</div>}
            <div className="syllabus-lesson-footer">
              <span className="syllabus-status-badge">{STATUS_LABELS[l.status] || l.status}</span>
              {l.status === "not_started" && (
                <button className="btn btn-primary" disabled={loading} onClick={() => startLesson(i)}>
                  {loading && activeIndex === i ? "בונה מערך שיעור..." : "התחל שיעור"}
                </button>
              )}
              {l.status === "in_progress" && l.session_id && (
                <button className="btn btn-primary" onClick={() => resumeLesson(l.session_id)}>המשך שיעור</button>
              )}
              {l.status === "completed" && l.session_id && (
                <button className="btn btn-ghost" onClick={() => resumeLesson(l.session_id)}>פתח שוב</button>
              )}
            </div>
          </div>
        ))}
      </div>

      {error && <p className="setup-error">{error}</p>}
    </div>
  );
}
