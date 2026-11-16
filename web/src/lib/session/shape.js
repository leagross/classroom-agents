/**
 * One mapper from a server session payload to the shape the UI holds.
 *
 * Classroom.jsx used to build this shape in two places — a helper for
 * resuming a session, and an inline object literal for a freshly created
 * one — which had to be kept in sync by hand and had already drifted (the
 * fresh path hard-coded activityIndex: 0 instead of reading the response).
 */
export function sessionFromServer(data) {
  return {
    id: data.session_id,
    topic: data.topic,
    poolNames: (data.pool || []).map((a) => a.name),
    history: (data.history || []).map((m) => ({
      agent: m.agent,
      key: m.key,
      color: m.color,
      text: m.text,
      isUser: m.is_user,
    })),
    plan: data.plan,
    activityIndex: data.activity_index || 0,
    awaitingUser: data.awaiting_user,
    teacherMode: data.teacher_mode || null,
    syllabusId: data.syllabus_id || null,
  };
}
