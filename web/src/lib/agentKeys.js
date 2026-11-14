// Stable agent keys shared with the backend (backend/agents.py Agent.key).
// Only the teacher's key is needed on the frontend today — e.g. to decide
// whether the currently-streaming speaker is the one who gets to write on
// the lesson board.
export const TEACHER_KEY = "teacher";
