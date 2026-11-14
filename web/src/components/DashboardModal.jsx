import { useEffect, useState } from "react";
import { getDashboard } from "../lib/api/dashboard";
import "./DashboardModal.css";

export default function DashboardModal({ open, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    getDashboard().then((d) => {
      setData(d);
      setLoading(false);
    });
  }, [open]);

  if (!open) return null;

  return (
    <div className="modal-overlay open" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal dashboard-modal">
        <button className="modal-close" onClick={onClose}>✕</button>
        <h3>ההתקדמות שלי</h3>

        {loading && <p>טוען...</p>}
        {!loading && !data && <p>התחבר עם Google כדי לראות את ההתקדמות שלך.</p>}

        {!loading && data && (
          <>
            <div className="dashboard-stats">
              <div className="stat-tile">
                <div className="stat-num">{data.total_lessons}</div>
                <div className="stat-label">שיעורים</div>
              </div>
              <div className="stat-tile">
                <div className="stat-num">{data.completed_lessons}</div>
                <div className="stat-label">הושלמו</div>
              </div>
              <div className="stat-tile">
                <div className="stat-num">{data.in_progress_lessons}</div>
                <div className="stat-label">בתהליך</div>
              </div>
              <div className="stat-tile">
                <div className="stat-num">{data.syllabi.length}</div>
                <div className="stat-label">סילבוסים</div>
              </div>
            </div>

            {data.topics_covered.length > 0 && (
              <>
                <h4>נושאים שנלמדו</h4>
                <div className="topics-chips">
                  {data.topics_covered.map((t, i) => <span className="topic-chip" key={i}>{t}</span>)}
                </div>
              </>
            )}

            {data.syllabi.length > 0 && (
              <>
                <h4>סילבוסים</h4>
                <div className="dashboard-syllabi">
                  {data.syllabi.map((s) => (
                    <div className="dashboard-syllabus-row" key={s.id}>
                      <span>{s.topic}</span>
                      <span className="syllabus-progress">{s.completed_lessons}/{s.total_lessons}</span>
                    </div>
                  ))}
                </div>
              </>
            )}

            {data.total_lessons === 0 && data.syllabi.length === 0 && (
              <p>עוד לא התחלת שיעור. ברגע שתתחיל, ההתקדמות שלך תופיע כאן.</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
