import { useState } from "react";
import { DEPTH_OPTIONS, LEVEL_LABEL, LEVEL_OPTIONS, TIME_OPTIONS } from "../lib/intake";
import DiagnosticModal from "./DiagnosticModal";
import "./IntakeFields.css";

/**
 * Stage 1's questions: how long, how deep, from what level, and why.
 * Shared by the single-lesson form and the syllabus form, which both need
 * exactly the same answers before anything is planned.
 *
 * The level can be stated, or — for someone who isn't sure, or who would
 * rather have it checked — placed by a short quiz. Which of the two it was
 * is remembered, because the teacher is told: people mis-rate themselves in
 * both directions.
 */
export default function IntakeFields({ topic, value, onChange, timeLabel = "כמה זמן יש לך?", disabled }) {
  const [diagnosing, setDiagnosing] = useState(false);
  const set = (patch) => onChange({ ...value, ...patch });
  const canDiagnose = topic.trim().length > 0 && !disabled;

  return (
    <div className="intake">
      <div className="intake-group">
        <label className="intake-label">{timeLabel}</label>
        <div className="intake-chips">
          {TIME_OPTIONS.map((o) => (
            <button
              key={o.value}
              type="button"
              className={"intake-chip" + (value.time_budget_minutes === o.value ? " selected" : "")}
              onClick={() => set({ time_budget_minutes: o.value })}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      <div className="intake-group">
        <label className="intake-label">לאיזה עומק אתה רוצה להגיע?</label>
        <div className="intake-chips">
          {DEPTH_OPTIONS.map((o) => (
            <button
              key={o.value}
              type="button"
              className={"intake-chip" + (value.target_depth === o.value ? " selected" : "")}
              onClick={() => set({ target_depth: o.value })}
              title={o.hint}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      <div className="intake-group">
        <label className="intake-label">מאיזו רמה אתה מתחיל?</label>
        <div className="intake-chips">
          {LEVEL_OPTIONS.map((o) => (
            <button
              key={o.value}
              type="button"
              className={"intake-chip" + (value.starting_level === o.value ? " selected" : "")}
              onClick={() => set({ starting_level: o.value, level_source: "stated" })}
              title={o.hint}
            >
              {o.label}
            </button>
          ))}
          <button
            type="button"
            className="intake-chip intake-diagnose"
            onClick={() => setDiagnosing(true)}
            disabled={!canDiagnose}
            title={canDiagnose ? "בוחן קצר שיקבע את הרמה" : "כתוב קודם את הנושא"}
          >
            לא בטוח — בדקו אותי
          </button>
        </div>
        {value.starting_level && value.level_source === "diagnosed" && (
          <p className="intake-note">הרמה נקבעה לפי הבוחן: {LEVEL_LABEL[value.starting_level]}. אפשר לשנות אותה למעלה.</p>
        )}
      </div>

      <div className="intake-group">
        <label className="intake-label">
          מה המטרה שלך? <span className="intake-optional">(לא חובה)</span>
        </label>
        <input
          className="intake-goal"
          placeholder="למשל: להתכונן למבחן, להבין מאמר, לעבוד עם זה בעבודה..."
          value={value.goal}
          onChange={(e) => set({ goal: e.target.value })}
        />
      </div>

      <DiagnosticModal
        open={diagnosing}
        topic={topic.trim()}
        onClose={() => setDiagnosing(false)}
        onResult={(level) => set({ starting_level: level, level_source: "diagnosed" })}
      />
    </div>
  );
}
