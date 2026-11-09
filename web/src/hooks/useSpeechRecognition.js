import { useEffect, useRef, useState } from "react";

export default function useSpeechRecognition(onResult, onStart) {
  const [supported, setSupported] = useState(true);
  const [listening, setListening] = useState(false);
  const recognizerRef = useRef(null);

  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setSupported(false);
      return;
    }
    const recognizer = new SpeechRecognition();
    recognizer.lang = "he-IL";
    recognizer.interimResults = false;
    recognizer.maxAlternatives = 1;
    recognizer.onresult = (event) => onResult(event.results[0][0].transcript);
    recognizer.onerror = () => setListening(false);
    recognizer.onend = () => setListening(false);
    recognizerRef.current = recognizer;
  }, [onResult]);

  function toggle() {
    const recognizer = recognizerRef.current;
    if (!recognizer) return;
    if (listening) {
      recognizer.stop();
    } else {
      onStart?.();
      setListening(true);
      try { recognizer.start(); } catch (e) { setListening(false); }
    }
  }

  return { supported, listening, toggle };
}
