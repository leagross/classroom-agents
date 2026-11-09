import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getMe, getMyLessons } from "../lib/api";
import "./Sidebar.css";

const RECENT_LESSONS_STORAGE = "classroom_recent_lessons";
const RECENT_LESSONS_MAX = 15;

export function getRecentLessons() {
  try {
    return JSON.parse(localStorage.getItem(RECENT_LESSONS_STORAGE) || "[]");
  } catch (e) {
    return [];
  }
}

export function saveRecentLesson(id, topic, poolNames) {
  let list = getRecentLessons().filter((l) => l.id !== id);
  list.unshift({ id, topic, poolNames, ts: Date.now() });
  list = list.slice(0, RECENT_LESSONS_MAX);
  localStorage.setItem(RECENT_LESSONS_STORAGE, JSON.stringify(list));
}

export default function Sidebar({ activeSessionId, onNewLesson, onSelectLesson, refreshKey }) {
  const [serverLessons, setServerLessons] = useState([]);
  const [localLessons, setLocalLessons] = useState([]);

  useEffect(() => {
    setLocalLessons(getRecentLessons());
    getMe().then((me) => {
      if (me) getMyLessons().then(setServerLessons);
    });
  }, [refreshKey, activeSessionId]);

  const empty = serverLessons.length === 0 && localLessons.length === 0;

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <Link to="/" className="sidebar-home-link">
          <h2 className="gradient-text">כיתה של סוכנים</h2>
        </Link>
        <button className="new-lesson-btn" onClick={onNewLesson}>+ שיעור חדש</button>
      </div>

      <div className="sidebar-lessons">
        {serverLessons.length > 0 && (
          <>
            <h4>השיעורים שלי</h4>
            {serverLessons.map((l) => (
              <LessonItem
                key={l.id}
                id={l.id}
                topic={l.topic}
                meta={new Date(l.created_at).toLocaleDateString("he-IL")}
                active={l.id === activeSessionId}
                onClick={onSelectLesson}
              />
            ))}
          </>
        )}

        {localLessons.length > 0 && (
          <>
            <h4>שיעורים אחרונים בדפדפן הזה</h4>
            {localLessons.map((l) => (
              <LessonItem
                key={l.id}
                id={l.id}
                topic={l.topic}
                meta={(l.poolNames || []).join(", ")}
                active={l.id === activeSessionId}
                onClick={onSelectLesson}
              />
            ))}
          </>
        )}

        {empty && <div className="sidebar-empty-hint">עדיין אין שיעורים. התחל שיעור חדש כדי לראות אותו כאן.</div>}
      </div>
    </aside>
  );
}

function LessonItem({ id, topic, meta, active, onClick }) {
  return (
    <div className={"sidebar-lesson" + (active ? " active" : "")} onClick={() => onClick(id)}>
      <div className="lesson-topic">{topic}</div>
      <div className="lesson-meta">{meta}</div>
    </div>
  );
}
