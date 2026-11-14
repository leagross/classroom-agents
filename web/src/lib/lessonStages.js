// Hebrew display labels for the 5-stage pedagogical model a lesson plan's
// activities follow — mirrors backend/agents.py's LESSON_STAGE_LABELS.
export const STAGE_LABELS = {
  opening: "פתיח",
  teaching: "לימוד/הקנייה",
  practice: "תרגול/התנסות",
  assessment: "הערכה",
  summary: "סיכום",
};

export function stageLabel(stage) {
  return STAGE_LABELS[stage] || stage;
}
