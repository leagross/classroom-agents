import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import NavBar from "../components/NavBar";
import { getMe, getBillingStatus, startCheckout } from "../lib/api";
import "./Pricing.css";

const FREE_FEATURES = [
  "כל 6 הדמויות בכיתה",
  "שיחה קולית (מיקרופון + הקראה)",
  "בוחן בסוף כל שיעור",
  "עד 3 שיעורים חדשים בחודש",
];

const PREMIUM_FEATURES = [
  "כל מה שיש בתוכנית החינמית",
  "ללא הגבלת שיעורים",
  "היסטוריה מסונכרנת בכל המכשירים",
  "עדיפות לתכונות חדשות",
];

export default function Pricing() {
  const [me, setMe] = useState(null);
  const [billing, setBilling] = useState(null);
  const [loadingPlan, setLoadingPlan] = useState(null);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    getMe().then(setMe);
    getBillingStatus().then(setBilling);
  }, []);

  async function handleUpgrade() {
    setError("");
    if (!me) {
      window.location.href = "/auth/google/login?next=/pricing";
      return;
    }
    setLoadingPlan("premium");
    try {
      const { url } = await startCheckout("premium");
      window.location.href = url;
    } catch (e) {
      setError(e.message || "לא הצלחנו לפתוח את עמוד התשלום. נסה שוב.");
      setLoadingPlan(null);
    }
  }

  const currentPlan = billing?.plan || "free";

  return (
    <div className="pricing-page">
      <NavBar />
      <div className="container pricing-container">
        <h1 className="pricing-title">תוכניות ומחירים</h1>
        <p className="pricing-sub">תתחילו בחינם, שדרגו כשתרצו ללא הגבלה.</p>

        {error && <p className="pricing-error">{error}</p>}

        <div className="plans-grid">
          <div className={"plan-card" + (currentPlan === "free" ? " current" : "")}>
            <h3>חינמי</h3>
            <div className="plan-price">₪0<span>/חודש</span></div>
            <ul>
              {FREE_FEATURES.map((f) => <li key={f}>✓ {f}</li>)}
            </ul>
            {currentPlan === "free" ? (
              <button className="btn btn-ghost" disabled>התוכנית הנוכחית שלך</button>
            ) : (
              <button className="btn btn-ghost" onClick={() => navigate("/app")}>כניסה לכיתה</button>
            )}
          </div>

          <div className={"plan-card featured" + (currentPlan === "premium" ? " current" : "")}>
            <div className="plan-badge">הכי פופולרי</div>
            <h3>פרימיום</h3>
            <div className="plan-price">$9.99<span>/חודש</span></div>
            <ul>
              {PREMIUM_FEATURES.map((f) => <li key={f}>✓ {f}</li>)}
            </ul>
            {currentPlan === "premium" ? (
              <button className="btn btn-primary" disabled>התוכנית הנוכחית שלך</button>
            ) : (
              <button className="btn btn-primary" onClick={handleUpgrade} disabled={loadingPlan === "premium"}>
                {loadingPlan === "premium" ? "טוען..." : "שדרג לפרימיום"}
              </button>
            )}
          </div>
        </div>

        <p className="pricing-note">
          כל התוכניות דורשות מפתח Anthropic (Claude) אישי משלך — השירות לא גובה תשלום על שימוש ב-AI, רק על תכונות הפלטפורמה.
        </p>
      </div>
    </div>
  );
}
