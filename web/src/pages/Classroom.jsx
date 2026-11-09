import { useState } from "react";
import Sidebar, { saveRecentLesson } from "../components/Sidebar";
import SetupForm from "../components/SetupForm";
import ChatPanel from "../components/ChatPanel";
import SettingsModal from "../components/SettingsModal";
import QuizModal from "../components/QuizModal";
import AuthArea from "../components/AuthArea";
import { createSession, getSession, getStoredApiKey } from "../lib/api";
import "./Classroom.css";

export default function Classroom() {
  const [session, setSession] = useState(null); // { id, topic, poolNames, history }
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [quizOpen, setQuizOpen] = useState(false);
  const [hasKey, setHasKey] = useState(!!getStoredApiKey());
  const [sidebarRefresh, setSidebarRefresh] = useState(0);

  function bumpSidebar() {
    setSidebarRefresh((n) => n + 1);
  }

  async function handleStart(topic, poolKeys) {
    try {
      const data = await createSession(topic, poolKeys);
      const poolNames = data.pool.map((a) => a.name);
      saveRecentLesson(data.session_id, data.topic, poolNames);
      setSession({ id: data.session_id, topic: data.topic, poolNames, history: [] });
      bumpSidebar();
    } catch (e) {
      alert(e.message || "בחר בדיוק 2 תלמידים, או אל תבחר כלל (בחירה אוטומטית).");
    }
  }

  async function handleSelectLesson(id) {
    try {
      const data = await getSession(id);
      const poolNames = data.pool.map((a) => a.name);
      const history = data.history.map((m) => ({
        agent: m.agent, key: m.key, color: m.color, text: m.text, isUser: m.is_user,
      }));
      setSession({ id: data.session_id, topic: data.topic, poolNames, history });
      bumpSidebar();
    } catch (e) {
      alert("לא הצלחתי לטעון את השיעור הזה (אולי נמחק עם ריסטרט שרת בלי DB מחובר).");
    }
  }

  function handleNewLesson() {
    setSession(null);
    bumpSidebar();
  }

  function handleApiKeyError(detail) {
    alert(detail);
    setSettingsOpen(true);
  }

  return (
    <div className="classroom-layout">
      <Sidebar
        activeSessionId={session?.id}
        onNewLesson={handleNewLesson}
        onSelectLesson={handleSelectLesson}
        refreshKey={sidebarRefresh}
      />

      <div className="classroom-main">
        <div className="classroom-topbar">
          <button className="settings-btn" title="מפתח API אישי" onClick={() => setSettingsOpen(true)}>🔑</button>
          <div className="spacer" />
          <AuthArea refreshKey={sidebarRefresh} />
        </div>

        <div className="classroom-content">
          {!session ? (
            <SetupForm hasApiKey={hasKey} onOpenSettings={() => setSettingsOpen(true)} onStart={handleStart} />
          ) : (
            <ChatPanel
              sessionId={session.id}
              topic={session.topic}
              poolNames={session.poolNames}
              initialHistory={session.history}
              onHome={handleNewLesson}
              onOpenQuiz={() => setQuizOpen(true)}
              onApiKeyError={handleApiKeyError}
            />
          )}
        </div>
      </div>

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onKeyChange={() => setHasKey(!!getStoredApiKey())}
      />
      {session && <QuizModal open={quizOpen} sessionId={session.id} onClose={() => setQuizOpen(false)} />}
    </div>
  );
}
