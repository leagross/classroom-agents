/**
 * Builds a single downloadable study sheet for a lesson: goals, whatever
 * was written on the lesson board (all pages), homework, and the quiz if
 * one was generated this session. Pure client-side (Blob download), same
 * spirit as LessonPlanPreview's Markdown export — no server round-trip.
 */
export function buildLessonSummaryMarkdown({ topic, poolNames, plan, boardPages, quizQuestions }) {
  const lines = [`# סיכום שיעור: ${topic}`, ""];

  if (poolNames?.length) {
    lines.push(`הרכב הכיתה: המורה, ${poolNames.join(", ")}`, "");
  }

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

  if (plan?.homework) {
    lines.push("## שיעורי בית", plan.homework, "");
  }

  if (quizQuestions?.length) {
    lines.push("## בוחן על השיעור");
    quizQuestions.forEach((q, i) => {
      lines.push(`${i + 1}. ${q.question}`);
      q.options.forEach((opt, oi) => {
        lines.push(`   - ${opt}${oi === q.correct_index ? " ✓" : ""}`);
      });
      if (q.explanation) lines.push(`   (${q.explanation})`);
      lines.push("");
    });
  }

  return lines.join("\n");
}

export function downloadLessonSummary(summaryData) {
  const md = buildLessonSummaryMarkdown(summaryData);
  const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `סיכום-שיעור-${summaryData.topic}.md`;
  a.click();
  URL.revokeObjectURL(url);
}
