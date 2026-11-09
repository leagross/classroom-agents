import { useEffect, useRef, useState } from "react";
import { sendMessageStream } from "../lib/api";
import useSpeechRecognition from "../hooks/useSpeechRecognition";
import useTextToSpeech from "../hooks/useTextToSpeech";
import renderMath from "../hooks/useMathRender";
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

export default function ChatPanel({ sessionId, topic, poolNames, initialHistory, onHome, onOpenQuiz, onApiKeyError }) {
  const [messages, setMessages] = useState(initialHistory || []);
  const [input, setInput] = useState("");
  const [pendingImage, setPendingImage] = useState(null);
  const [streaming, setStreaming] = useState(null); // {name, color, text}
  const [waiting, setWaiting] = useState(false);
  const chatRef = useRef(null);
  const fileInputRef = useRef(null);
  const streamingElRef = useRef(null);
  const tts = useTextToSpeech();

  useEffect(() => {
    setMessages(initialHistory || []);
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

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

    let accumulated = "";
    let current = { name: "", color: "" };
    await sendMessageStream(sessionId, text || "(התלמיד צירף תמונה בלי טקסט נוסף)", image, (evt) => {
      setWaiting(false);
      if (evt.type === "start") {
        accumulated = "";
        current = { name: evt.name, color: evt.color };
        setStreaming({ name: evt.name, color: evt.color, text: "" });
      } else if (evt.type === "token") {
        accumulated += evt.text;
        setStreaming((prev) => (prev ? { ...prev, text: accumulated } : prev));
      } else if (evt.type === "end") {
        setMessages((prev) => [...prev, { agent: current.name, key: "assistant", color: current.color, text: accumulated, isUser: false }]);
        setStreaming(null);
        tts.speak(accumulated);
      } else if (evt.type === "error") {
        setStreaming(null);
        if (evt.detail && evt.detail.includes("מפתח")) onApiKeyError(evt.detail);
        else alert(evt.detail || "שגיאה בשליחת ההודעה.");
      }
    });
    setWaiting(false);
  }

  useEffect(() => {
    if (streamingElRef.current && streaming) {
      // live-stream text isn't math-rendered mid-flight (unbalanced LaTeX risk);
      // only the scroll position needs to track it.
      chatRef.current && (chatRef.current.scrollTop = chatRef.current.scrollHeight);
    }
  }, [streaming]);

  return (
    <div className="chat-panel">
      <div className="topic-bar">
        <button className="home-btn" onClick={onHome} title="חזרה לדף הבית">🏠</button>
        <span className="topic-text">נושא: {topic} · הרכב הכיתה: המורה, {(poolNames || []).join(", ")}</span>
        <button className="quiz-btn" onClick={onOpenQuiz}>📝 בוחן על השיעור</button>
      </div>

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
