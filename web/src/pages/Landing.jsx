import { Link } from "react-router-dom";
import NavBar from "../components/NavBar";
import "./Landing.css";

const STATS = [
  { value: "6", label: "דמויות בכיתה", sub: "מורה, תלמידים ובדחן" },
  { value: "24/7", label: "זמינה תמיד", sub: "כל שעה, כל נושא" },
  { value: "∞", label: "נושאי לימוד", sub: "מתמטיקה ועד היסטוריה" },
];

export default function Landing() {
  return (
    <div className="landing">
      <NavBar />

      <header className="hero">
        <div className="container hero-grid">
          <div className="hero-copy">
            <p className="eyebrow">חוג לימוד פרטי מבוסס AI</p>
            <h1>
              כיתה של <span className="gradient-text">סוכנים</span>
            </h1>
            <p className="hero-sub">
              מורה וירטואלי שמלמד, מתלמידים שמתלבטים איתך, ומעמיק ששואל "אבל מה אם..." —
              כל זה בשיחה אחת, על כל נושא שתבחר.
            </p>
            <div className="hero-actions">
              <Link to="/app" className="btn btn-primary">התחל שיעור בחינם</Link>
              <Link to="/pricing" className="btn btn-ghost">לתוכניות ולמחירים</Link>
            </div>
          </div>
          <div className="hero-visual" aria-hidden="true">
            <div className="chat-mock">
              <div className="chat-mock-bubble teacher">בואו נתחיל: מה אתם יודעים על פוטוסינתזה?</div>
              <div className="chat-mock-bubble student">אה, חשבתי שזה קשור לנשימה... לא?</div>
              <div className="chat-mock-bubble deep">כן, אבל מה קורה בלילה, כשאין שמש?</div>
            </div>
          </div>
        </div>
      </header>

      <section className="stats">
        <div className="container stats-grid">
          {STATS.map((s) => (
            <div className="stat-card" key={s.label}>
              <div className="stat-value gradient-text">{s.value}</div>
              <div className="stat-label">{s.label}</div>
              <div className="stat-sub">{s.sub}</div>
            </div>
          ))}
        </div>
      </section>

      <section id="how-it-works" className="how">
        <div className="container">
          <h2>איך זה עובד</h2>
          <div className="how-grid">
            <div className="how-card">
              <div className="how-num">1</div>
              <h3>בוחרים נושא</h3>
              <p>מתמטיקה, היסטוריה, פיזיקה — כל נושא שבא לכם ללמוד.</p>
            </div>
            <div className="how-card">
              <div className="how-num">2</div>
              <h3>הכיתה מתכנסת</h3>
              <p>המורה ועוד שני "תלמידים" נבחרים אוטומטית לפי הנושא.</p>
            </div>
            <div className="how-card">
              <div className="how-num">3</div>
              <h3>לומדים דרך שיחה</h3>
              <p>שואלים, מתווכחים, מקבלים בוחן בסוף — ממשיכים בכל זמן.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="cta-banner">
        <div className="container cta-inner">
          <h2>מוכנים להתחיל?</h2>
          <p>השיעור הראשון על הבית.</p>
          <Link to="/app" className="btn btn-primary">כניסה לכיתה</Link>
        </div>
      </section>
    </div>
  );
}
