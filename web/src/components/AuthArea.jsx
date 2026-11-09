import { useEffect, useState } from "react";
import { getAuthStatus, getMe, logout } from "../lib/api";
import "./AuthArea.css";

export default function AuthArea({ refreshKey }) {
  const [configured, setConfigured] = useState(false);
  const [user, setUser] = useState(null);

  useEffect(() => {
    getAuthStatus().then((s) => setConfigured(s.configured));
    getMe().then(setUser);
  }, [refreshKey]);

  if (!configured) return null;

  if (!user) {
    return (
      <button className="sign-in-btn" onClick={() => (window.location.href = "/auth/google/login")}>
        התחברות עם Google
      </button>
    );
  }

  return (
    <div className="auth-area">
      {user.picture && <img src={user.picture} alt="" />}
      <span>{user.name || user.email}</span>
      <button
        className="logout-btn"
        onClick={async () => {
          await logout();
          setUser(null);
        }}
      >
        התנתק
      </button>
    </div>
  );
}
