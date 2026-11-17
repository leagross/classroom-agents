import { useState } from "react";
import { generateSyllabus, createSyllabus } from "../lib/api/syllabus";
import usePreviewFlow from "../hooks/usePreviewFlow";
import { EMPTY_INTAKE, isIntakeComplete, missingHint, toProfile } from "../lib/intake";
import IntakeFields from "./IntakeFields";
import "./SetupForm.css";
import "./SyllabusList.css";

/**
 * Entry point for the "syllabus" flow: a broad topic is broken into a
 * lesson outline (title + summary each) up front; each lesson's own full
 * 5-stage plan is generated later, lazily, only once the student starts it
 * (see SyllabusView). This component only produces the outline and, once
 * approved, a persisted syllabus — it never touches lesson_plan.py itself.
 */
export default function SyllabusBuilder({ hasApiKey, onOpenSettings, onSyllabusReady }) {
  const [topic, setTopic] = useState("");
  const [intake, setIntake] = useState(EMPTY_INTAKE);
  const { preview, loading, error, run, cancel, submit } = usePreviewFlow((t) =>
    generateSyllabus(t, toProfile(t, intake))
  );

  async function buildPreview() {
    if (!hasApiKey) { onOpenSettings(); return; }
    if (!isIntakeComplete(topic, intake)) return;
    await run(topic.trim());
  }

  async function approve() {
    const syllabus = await submit(() => createSyllabus(preview.topic, preview.lessons, preview.profile));
    if (syllabus) onSyllabusReady(syllabus);
  }

  if (preview) {
    return (
      <div className="setup">
        <h2>סילבוס: {preview.topic}</h2>
        <p className="subtitle">{preview.lessons.length} שיעורים מתוכננים — כל שיעור יתוכנן במלואו רק כשתתחיל אותו</p>

        <div className="syllabus-lessons">
          {preview.lessons.map((l, i) => (
            <div className="syllabus-lesson-row" key={i}>
              <div className="syllabus-lesson-title">{i + 1}. {l.title}</div>
              {l.summary && <div className="syllabus-lesson-summary">{l.summary}</div>}
            </div>
          ))}
        </div>

        {error && <p className="setup-error">{error}</p>}

        <div className="plan-actions">
          <button className="btn btn-primary" onClick={approve} disabled={loading}>
            {loading ? "שומר..." : "אשר סילבוס והתחל"}
          </button>
          <button className="btn btn-ghost" onClick={buildPreview} disabled={loading}>ייצר מחדש</button>
          <button className="btn btn-ghost" onClick={cancel} disabled={loading}>ביטול</button>
        </div>
      </div>
    );
  }

  return (
    <div className="setup">
      <h2>סילבוס חדש</h2>
      <p className="subtitle">נושא רחב שמתחלק לכמה שיעורים</p>

      <p>איזה נושא רחב תרצה ללמד?</p>
      <input
        placeholder="למשל: מלחמת העולם השנייה, יסודות הפייתון, האימפרסיוניזם..."
        value={topic}
        onChange={(e) => setTopic(e.target.value)}
      />

      <IntakeFields
        topic={topic}
        value={intake}
        onChange={setIntake}
        timeLabel="כמה זמן אתה יכול להקדיש לכל שיעור?"
      />

      {error && <p className="setup-error">{error}</p>}
      {!isIntakeComplete(topic, intake) && <p className="intake-hint">{missingHint(topic, intake)}</p>}

      <button
        className="btn btn-primary"
        disabled={!hasApiKey || loading || !isIntakeComplete(topic, intake)}
        onClick={buildPreview}
      >
        {loading ? "בונה סילבוס..." : "הצע סילבוס"}
      </button>
    </div>
  );
}
