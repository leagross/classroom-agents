import { Link } from "react-router-dom";
import "./NavBar.css";

export default function NavBar() {
  return (
    <nav className="navbar">
      <div className="container navbar-inner">
        <Link to="/" className="navbar-logo">
          <span className="gradient-text">כיתה של סוכנים</span>
        </Link>
        <div className="navbar-links">
          <Link to="/pricing">מחירים</Link>
          <a href="#how-it-works">איך זה עובד</a>
          <Link to="/app" className="btn btn-primary navbar-cta">כניסה לכיתה</Link>
        </div>
      </div>
    </nav>
  );
}
