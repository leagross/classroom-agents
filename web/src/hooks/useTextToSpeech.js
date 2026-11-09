import { useEffect, useRef, useState } from "react";

const TTS_STORAGE = "classroom_tts_enabled";

export default function useTextToSpeech() {
  const [supported] = useState("speechSynthesis" in window);
  const [enabled, setEnabled] = useState(localStorage.getItem(TTS_STORAGE) === "1");
  const voiceRef = useRef(null);

  useEffect(() => {
    if (!supported) return;
    function pickVoice() {
      const voices = window.speechSynthesis.getVoices();
      voiceRef.current = voices.find((v) => v.lang?.toLowerCase().startsWith("he")) || null;
    }
    pickVoice();
    window.speechSynthesis.onvoiceschanged = pickVoice;
  }, [supported]);

  function toggle() {
    setEnabled((prev) => {
      const next = !prev;
      localStorage.setItem(TTS_STORAGE, next ? "1" : "0");
      if (!next && supported) window.speechSynthesis.cancel();
      return next;
    });
  }

  function speak(text) {
    if (!supported || !enabled || !text) return;
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "he-IL";
    if (voiceRef.current) utter.voice = voiceRef.current;
    window.speechSynthesis.speak(utter);
  }

  function cancel() {
    if (supported) window.speechSynthesis.cancel();
  }

  return { supported, enabled, toggle, speak, cancel };
}
