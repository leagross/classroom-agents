/**
 * Stage 1's choices, and where intake stands.
 *
 * `missingStep` mirrors the server's IntakeFlow.from_partial: the same walk
 * (topic -> time + depth -> level), stopping at the first thing missing. The
 * server is what enforces it; this only lets the form say what is left and
 * keep the button disabled until it is done, without a round trip.
 */

export const TIME_OPTIONS = [
  { value: 15, label: "15 דקות" },
  { value: 30, label: "30 דקות" },
  { value: 45, label: "45 דקות" },
  { value: 60, label: "שעה" },
  { value: 90, label: "שעה וחצי" },
  { value: 120, label: "שעתיים" },
];

export const DEPTH_OPTIONS = [
  { value: "basics", label: "יסודות", hint: "להבין את הרעיון המרכזי" },
  { value: "practical", label: "שימושי", hint: "לדעת מה עושים עם זה בפועל" },
  { value: "expert", label: "מעמיק-מקצועי", hint: "כולל דיוק ומקרי קצה" },
];

export const LEVEL_OPTIONS = [
  { value: "beginner", label: "מתחיל", hint: "כמעט לא פגשתי את הנושא" },
  { value: "intermediate", label: "בינוני", hint: "מכיר את היסודות" },
  { value: "expert", label: "מתקדם", hint: "מכיר את התחום היטב" },
];

export const LEVEL_LABEL = Object.fromEntries(LEVEL_OPTIONS.map((o) => [o.value, o.label]));

export const EMPTY_INTAKE = {
  time_budget_minutes: null,
  target_depth: null,
  starting_level: null,
  level_source: "stated",
  goal: "",
};

const STEP_HINTS = {
  topic: "כתוב קודם את הנושא.",
  context: "בחר כמה זמן יש לך, ולאיזה עומק אתה רוצה להגיע.",
  level: "בחר את רמת הפתיחה שלך, או עשה בוחן קצר שיקבע אותה.",
};

/** "topic" | "context" | "level" | null (complete). */
export function missingStep(topic, intake) {
  if (!topic.trim()) return "topic";
  if (!intake.time_budget_minutes || !intake.target_depth) return "context";
  if (!intake.starting_level) return "level";
  return null;
}

export function missingHint(topic, intake) {
  const step = missingStep(topic, intake);
  return step ? STEP_HINTS[step] : "";
}

export function isIntakeComplete(topic, intake) {
  return missingStep(topic, intake) === null;
}

/** The profile as the server expects it. */
export function toProfile(topic, intake) {
  return { ...intake, topic: topic.trim() };
}
