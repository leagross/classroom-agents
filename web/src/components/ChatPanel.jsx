import { useEffect, useRef, useState } from "react";
import { sendMessageStream } from "../lib/api/chat";
import useSpeechRecognition from "../hooks/useSpeechRecognition";
import useTextToSpeech from "../hooks/useTextToSpeech";
import useLessonAutoplay from "../hooks/useLessonAutoplay";
import renderMath from "../hooks/useMathRender";
import { stageLabel } from "../lib/lessonStages";
import { TEACHER_KEY } from "../lib/agentKeys";
import LessonBoard from "./LessonBoard";
import "./ChatPanel.css";

const ALLOWED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

function initials(name) {
  return (name || "").replace(/^ה/, "").slice(0, 2);
}

function Avatar({ name, color, small }) {
  return (
    <div className={"avatar" + (small ? " sm" : "")} style={{ background: color }}>
      {initials(name)}
    </div>
  );
}

export default function ChatPanel({
  sessionId, topic, poolNames, initialHistory,
  plan, initialActivityIndex, initialAwaitingUser,
  onHome, onOpenQuiz, onApiKeyError,
}) {
  const [messages, setMessages] = useState(initialHistory || []);
  const [input, setInput] = useState("");
  const [pendingImage, setPendingImage] = useState(null);
  const [streaming, setStreaming] = useState(null); // {name, color, text}
  const [waiting, setWaiting] = useState(false);
  const [board, setBoard] = useState(null); // {text, isLive} — plan-driven lessons only, teacher beats only
  const chatRef = useRef(null);
  const fileInputRef = useRef(null);
  const streamingElRef = useRef(null);
  const tts = useTextToSpeech();

  const { activityIndex, preempt, handleDone } = useLessonAutoplay({
    sessionId, plan, initialActivityIndex, initialAwaitingUser, runStream,
  });

  useEffect(() => {
    setMessages(initialHistory || []);
    setBoard(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [messages, streaming]);

  useEffect(() => {
    if (!streaming && chatRef.current) renderMath(chatRef.current);
  }, [streaming]);

  const { supported: micSupported, listening, toggle: toggleMic } = useSpeechRecognition(
    (transcript) => setInput((prev) => (prev ? prev + " " : "") + transcript),
    () => tts.cancel()
  );

  /** Wires a streaming call's events to the chat UI, returns the final "done" event. */
  async function runStream(callStreamFn) {
    let accumulated = "";
    let current = { name: "", color: "", key: "" };
    let doneEvent = null;
    await callStreamFn((evt) => {
      setWaiting(false);
      if (evt.type === "start") {
        accumulated = "";
        current = { name: evt.name, color: evt.color, key: evt.key };
        setStreaming({ name: evt.name, color: evt.color, text: "" });
        if (plan && evt.key === TEACHER_KEY) setBoard({ text: "", isLive: true });
      } else if (evt.type === "token") {
        accumulated += evt.text;
        setStreaming((prev) => (prev ? { ...prev, text: accumulated } : prev));
        if (plan && current.key === TEACHER_KEY) setBoard({ text: accumulated, isLive: true });
      } else if (evt.type === "end") {
        setMessages((prev) => [...prev, { agent: current.name, key: "assistant", color: current.color, text: accumulated, isUser: false }]);
        setStreaming(null);
        tts.speak(accumulated);
        if (plan && current.key === TEACHER_KEY) setBoard({ text: accumulated, isLive: false });
      } else if (evt.type === "done") {
        doneEvent = evt;
      } else if (evt.type === "error") {
        setStreaming(null);
        if (evt.detail && evt.detail.includes("מפתח")) onApiKeyError(evt.detail);
        else alert(evt.detail || "שגיאה.");
        doneEvent = { type: "error" };
      }
    });
    return doneEvent;
  }

  function onFileChange(e) {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
      alert("סוג קובץ לא נתמך. אפשר PNG, JPEG, WEBP או GIF.");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      alert("הקובץ גדול מדי (מקסימום 5MB).");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result;
      setPendingImage({ mediaType: file.type, base64: dataUrl.split(",")[1], dataUrl, fileName: file.name });
    };
    reader.readAsDataURL(file);
  }

  async function handleSend() {
    const text = input.trim();
    if (!text && !pendingImage) return;

    // The user taking their turn always wins over a scheduled autonomous beat.
    const myToken = preempt();

    const userMsg = {
      agent: "את/ה",
      key: "user",
      color: "#64748b",
      text: text || "(ללא טקסט)",
      isUser: true,
      imageDataUrl: pendingImage?.dataUrl || null,
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    const image = pendingImage ? { media_type: pendingImage.mediaType, data: pendingImage.base64 } : null;
    setPendingImage(null);
    setWaiting(true);

    const doneEvent = await runStream((onEvent) =>
      sendMessageStream(sessionId, text || "(התלמיד צירף תמונה בלי טקסט נוסף)", image, onEvent)
    );
    setWaiting(false);

    handleDone(doneEvent, myToken);
  }

  const currentActivity = plan?.activities?.[activityIndex];

  return (
    <div className="chat-panel">
      <div className="topic-bar">
        <button className="home-btn" onClick={onHome} title="חזרה לדף הבית">🏠</button>
        <span className="topic-text">
          נושא: {topic} · הרכב הכיתה: המורה, {(poolNames || []).join(", ")}
          {plan && currentActivity && ` · שלב ${Math.min(activityIndex + 1, plan.activities.length)}/${plan.activities.length} (${stageLabel(currentActivity.stage)}): ${currentActivity.title}`}
        </span>
        <button className="quiz-btn" onClick={onOpenQuiz}>📝 בוחן על השיעור</button>
      </div>

      {plan && <LessonBoard text={board?.text} isLive={board?.isLive} />}

      <div className="chat-messages" ref={chatRef}>
        {messages.map((m, i) => (
          <div className={"msg-row" + (m.isUser ? " user" : "")} key={i}>
            <Avatar name={m.isUser ? "את/ה" : m.agent} color={m.isUser ? "#64748b" : m.color} small />
            <div className={"msg" + (m.isUser ? " user-bubble" : " agent")} style={!m.isUser ? { background: m.color } : undefined}>
              <div className="msg-name">{m.isUser ? "את/ה" : m.agent}</div>
              {m.imageDataUrl && <img src={m.imageDataUrl} alt="" className="msg-image" />}
              <div>{m.text}</div>
            </div>
          </div>
        ))}

        {waiting && !streaming && (
          <div className="typing-row">
            <Avatar name="" color="#9ca3af" small />
            <div className="typing-bubble" style={{ background: "#9ca3af" }}>
              <span className="dot" /><span className="dot" /><span className="dot" />
            </div>
          </div>
        )}

        {streaming && (
          <div className="msg-row">
            <Avatar name={streaming.name} color={streaming.color} small />
            <div className="msg agent" style={{ background: streaming.color }} ref={streamingElRef}>
              <div className="msg-name">{streaming.name}</div>
              <div>{streaming.text}</div>
            </div>
          </div>
        )}
      </div>

      {pendingImage && (
        <div className="attach-preview show">
          <img src={pendingImage.dataUrl} alt="" />
          <span className="file-name">{pendingImage.fileName}</span>
          <button onClick={() => setPendingImage(null)}>✕ הסר</button>
        </div>
      )}

      <div className="input-bar">
        <input ref={fileInputRef} type="file" accept={ALLOWED_IMAGE_TYPES.join(",")} style={{ display: "none" }} onChange={onFileChange} />
        <button className="attach-btn" title="צרף תמונה (למשל שיעורי בית)" onClick={() => fileInputRef.current.click()}>📎</button>
        <button
          className={"mic-btn" + (listening ? " listening" : "")}
          title={micSupported ? "הקלטה קולית" : "הדפדפן הזה לא תומך בהקלטה קולית"}
          disabled={!micSupported}
          onClick={toggleMic}
        >🎤</button>
        <input
          className="message-input"
          placeholder="כתוב כאן, או לחץ על המיקרופון..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
        />
        <button className="send-btn" onClick={handleSend}>➤</button>
        <button
          className={"tts-btn" + (tts.enabled ? " active" : "")}
          title={tts.supported ? (tts.enabled ? "הקראה פעילה (לחץ לכיבוי)" : "הקראת תשובות בקול") : "הדפדפן הזה לא תומך בהקראה"}
          disabled={!tts.supported}
          onClick={tts.toggle}
        >{tts.enabled ? "🔊" : "🔇"}</button>
      </div>
    </div>
  );
}
