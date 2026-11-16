/**
 * Markdown exports, in one place.
 *
 * There were two independent implementations of "build Markdown lines,
 * make a Blob, trigger a download" over overlapping lesson data — one for
 * the lesson plan, one for the end-of-lesson summary. The download half was
 * identical; only the lines differ, so that is the only part that is
 * written twice now.
 */

import { stageLabel } from "../lessonStages";

/** The one place that turns Markdown text into a downloaded .md file. */
export function downloadMarkdown(filename, markdown) {
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".md") ? filename : `${filename}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

/** The plan as approved before the lesson starts: goals and activities. */
export function buildLessonPlanMarkdown(topic, plan) {
  const lines = [`# מערך שיעור: ${topic}`, "", "## מטרות"];
  (plan.goals || []).forEach((g) => lines.push(`- ${g}`));
  lines.push("", "## פעילויות");
  (plan.activities || []).forEach((a, i) => {
    lines.push(`### ${i + 1}. ${stageLabel(a.stage)}: ${a.title}`);
    if (a.summary) lines.push(a.summary);
    lines.push(`- חילופי דברים אוטונומיים: ${a.autonomous_exchanges}`);
    lines.push(`- שאלת בדיקה: ${a.checkpoint_question}`);
    lines.push("");
  });
  if (plan.homework) lines.push("## שיעורי בית", plan.homework, "");
  return lines.join("\n");
}

/** The study sheet after the lesson: goals, the board, homework, quiz, cards. */
export function buildLessonSummaryMarkdown({ topic, poolNames, plan, boardPages, quizQuestions, flashcards }) {
  const lines = [`# סיכום שיעור: ${topic}`, ""];

  if (poolNames?.length) lines.push(`הרכב הכיתה: המורה, ${poolNames.join(", ")}`, "");

  if (plan?.goals?.length) {
    lines.push("## מטרות השיעור");
    plan.goals.forEach((g) => lines.push(`- ${g}`));
    lines.push("");
  }

  const notes = (boardPages || []).filter((page) => page && page.trim());
  if (notes.length) {
    lines.push("## מה שנכתב על הלוח");
    notes.forEach((page, i) => {
      if (notes.length > 1) lines.push(`### דף ${i + 1}`);
      lines.push(page, "");
    });
  }

  if (plan?.homework) lines.push("## שיעורי בית", plan.homework, "");

  if (quizQuestions?.length) {
    lines.push("## בוחן על השיעור");
    quizQuestions.forEach((q, i) => {
      lines.push(`${i + 1}. ${q.question}`);
      q.options.forEach((opt, oi) => lines.push(`   - ${opt}${oi === q.correct_index ? " ✓" : ""}`));
      if (q.explanation) lines.push(`   (${q.explanation})`);
      lines.push("");
    });
  }

  if (flashcards?.length) {
    lines.push("## כרטיסיות לחזרה");
    flashcards.forEach((c, i) => lines.push(`${i + 1}. **${c.front}** — ${c.back}`));
    lines.push("");
  }

  return lines.join("\n");
}

export function downloadLessonPlan(topic, plan) {
  downloadMarkdown(`מערך-שיעור-${topic}`, buildLessonPlanMarkdown(topic, plan));
}

export function downloadLessonSummary(summaryData) {
  downloadMarkdown(`סיכום-שיעור-${summaryData.topic}`, buildLessonSummaryMarkdown(summaryData));
}
