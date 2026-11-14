import { useState } from "react";
import Sidebar, { saveRecentLesson } from "../components/Sidebar";
import SetupForm from "../components/SetupForm";
import SyllabusBuilder from "../components/SyllabusBuilder";
import SyllabusView from "../components/SyllabusView";
import ChatPanel from "../components/ChatPanel";
import SettingsModal from "../components/SettingsModal";
import DashboardModal from "../components/DashboardModal";
import AuthArea from "../components/AuthArea";
import { createSession, getSession } from "../lib/api/session";
import { getSyllabus } from "../lib/api/syllabus";
import { getStoredApiKey } from "../lib/api/apiKey";
import "./Classroom.css";

function sessionFromServerData(data) {
  const poolNames = data.pool.map((a) => a.name);
  const history = (data.history || []).map((m) => ({
    agent: m.agent, key: m.key, color: m.color, text: m.text, isUser: m.is_user,
  }));
  return {
    id: data.session_id, topic: data.topic, poolNames, history,
    plan: data.plan, activityIndex: data.activity_index || 0, awaitingUser: data.awaiting_user,
    syllabusId: data.syllabus_id || null,
  };
}

export default function Classroom() {
  const [session, setSession] = useState(null); // { id, topic, poolNames, history, syllabusId, ... }
  const [syllabus, setSyllabus] = useState(null); // { id, topic, lessons } — the outline list view
  const [entryMode, setEntryMode] = useState("single"); // "single" | "syllabus" — only matters with no session/syllabus
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const [hasKey, setHasKey] = useState(!!getStoredApiKey());
  const [sidebarRefresh, setSidebarRefresh] = useState(0);

  function bumpSidebar() {
    setSidebarRefresh((n) => n + 1);
  }

  async function handleStart(topic, poolKeys, plan) {
    try {
      const data = await createSession(topic, poolKeys, plan);
      const poolNames = data.pool.map((a) => a.name);
      saveRecentLesson(data.session_id, data.topic, poolNames);
      setSession({
        id: data.session_id, topic: data.topic, poolNames, history: [],
        plan: data.plan, activityIndex: 0, awaitingUser: data.awaiting_user, syllabusId: null,
      });
      bumpSidebar();
    } catch (e) {
      alert(e.message || "בחר בדיוק 2 תלמידים, או אל תבחר כלל (בחירה אוטומטית).");
    }
  }

  async function handleSelectLesson(id) {
    try {
      const data = await getSession(id);
      saveRecentLesson(data.session_id, data.topic, data.pool.map((a) => a.name));
      setSession(sessionFromServerData(data));
      setSyllabus(null);
      bumpSidebar();
    } catch (e) {
      alert("לא הצלחתי לטעון את השיעור הזה (אולי נמחק עם ריסטרט שרת בלי DB מחובר).");
    }
  }

  /** Used by SyllabusView both for starting a fresh lesson and resuming one. */
  function handleSyllabusSessionStart(data) {
    saveRecentLesson(data.session_id, data.topic, data.pool.map((a) => a.name));
    setSession(sessionFromServerData(data));
    setSyllabus(null);
    bumpSidebar();
  }

  async function handleHome() {
    const syllabusId = session?.syllabusId;
    setSession(null);
    if (syllabusId) {
      try {
        setSyllabus(await getSyllabus(syllabusId));
      } catch (e) {
        setSyllabus(null);
      }
    }
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
        onNewLesson={() => { setSession(null); setSyllabus(null); bumpSidebar(); }}
        onSelectLesson={handleSelectLesson}
        refreshKey={sidebarRefresh}
      />

      <div className="classroom-main">
        <div className="classroom-topbar">
          <button className="settings-btn" title="מפתח API אישי" onClick={() => setSettingsOpen(true)}>🔑</button>
          <button className="settings-btn" title="ההתקדמות שלי" onClick={() => setDashboardOpen(true)}>📊</button>
          <div className="spacer" />
          <AuthArea refreshKey={sidebarRefresh} />
        </div>

        <div className="classroom-content">
          {session ? (
            <ChatPanel
              key={session.id}
              sessionId={session.id}
              topic={session.topic}
              poolNames={session.poolNames}
              initialHistory={session.history}
              plan={session.plan}
              initialActivityIndex={session.activityIndex}
              initialAwaitingUser={session.awaitingUser}
              onHome={handleHome}
              onApiKeyError={handleApiKeyError}
            />
          ) : syllabus ? (
            <SyllabusView
              syllabus={syllabus}
              onBack={() => setSyllabus(null)}
              onSessionStart={handleSyllabusSessionStart}
            />
          ) : (
            <div className="entry-screen">
              <div className="entry-mode-choice">
                <button
                  className={"entry-mode-btn" + (entryMode === "single" ? " selected" : "")}
                  onClick={() => setEntryMode("single")}
                >שיעור בודד</button>
                <button
                  className={"entry-mode-btn" + (entryMode === "syllabus" ? " selected" : "")}
                  onClick={() => setEntryMode("syllabus")}
                >סילבוס (כמה שיעורים)</button>
              </div>
              {entryMode === "single" ? (
                <SetupForm hasApiKey={hasKey} onOpenSettings={() => setSettingsOpen(true)} onStart={handleStart} />
              ) : (
                <SyllabusBuilder
                  hasApiKey={hasKey}
                  onOpenSettings={() => setSettingsOpen(true)}
                  onSyllabusReady={(syl) => setSyllabus(syl)}
                />
              )}
            </div>
          )}
        </div>
      </div>

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onKeyChange={() => setHasKey(!!getStoredApiKey())}
      />
      <DashboardModal open={dashboardOpen} onClose={() => setDashboardOpen(false)} />
    </div>
  );
}
