import { useEffect, useRef, useState } from "react";
import { gradeDiagnostic, startDiagnostic } from "../lib/api/intake";
import { LEVEL_LABEL } from "../lib/intake";
import renderMath from "../hooks/useMathRender";
import Modal from "./Modal";
import "./DiagnosticModal.css";

/**
 * 1.3 — a short quiz that places a student who isn't sure of their level.
 *
 * It is not a test to pass, and the dialog says so: someone who feels they
 * must score well will guess, which defeats the point. Skipping a question
 * is allowed and counts as "didn't know", which is exactly the information
 * being asked for.
 */
export default function DiagnosticModal({ open, topic, onClose, onResult }) {
  const [quiz, setQuiz] = useState(null); // { id, questions }
  const [answers, setAnswers] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const bodyRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    setQuiz(null);
    setAnswers([]);
    setResult(null);
    setError("");
    setBusy(true);
    startDiagnostic(topic)
      .then((data) => {
        if (cancelled) return;
        setQuiz(data);
        setAnswers(data.questions.map(() => null));
      })
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setBusy(false));
    return () => {
      cancelled = true;
    };
  }, [open, topic]);

  useEffect(() => {
    if (quiz && bodyRef.current) renderMath(bodyRef.current);
  }, [quiz]);

  function choose(questionIndex, optionIndex) {
    setAnswers((prev) => prev.map((a, i) => (i === questionIndex ? optionIndex : a)));
  }

  async function submit() {
    setBusy(true);
    setError("");
    try {
      setResult(await gradeDiagnostic(quiz.id, answers));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function accept() {
    onResult(result.level);
    onClose();
  }

  return (
    <Modal open={open} onClose={onClose} className="diagnostic-modal" title="בוחן היכרות קצר">
      <div ref={bodyRef}>
        {!result && (
          <p className="diagnostic-note">
            זה לא מבחן, ואין ציון שצריך להשיג. הוא רק עוזר לי להבין מאיפה להתחיל איתך. אם אינך יודע
            תשובה — עדיף לדלג מאשר לנחש.
          </p>
        )}

        {error && <p className="setup-error">{error}</p>}
        {busy && !quiz && !error && <p>בונה בוחן על "{topic}"...</p>}

        {quiz && !result && (
          <>
            {quiz.questions.map((q, qi) => (
              <div className="diagnostic-question" key={qi}>
                <div className="q-text">
                  {qi + 1}. {q.question}
                </div>
                {q.options.map((opt, oi) => (
                  <button
                    key={oi}
                    type="button"
                    className={"quiz-option" + (answers[qi] === oi ? " selected" : "")}
                    onClick={() => choose(qi, answers[qi] === oi ? null : oi)}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            ))}
            <button className="btn btn-primary" onClick={submit} disabled={busy}>
              {busy ? "בודק..." : "סיום"}
            </button>
          </>
        )}

        {result && (
          <div className="diagnostic-result">
            <p>
              ענית נכון על {result.correct} מתוך {result.total}. נתחיל מרמת{" "}
              <b>{LEVEL_LABEL[result.level]}</b>.
            </p>
            <p className="diagnostic-note">אפשר לשנות את זה ידנית אחר כך אם זה לא מרגיש נכון.</p>
            <button className="btn btn-primary" onClick={accept}>
              מתחילים
            </button>
          </div>
        )}
      </div>
    </Modal>
  );
}
