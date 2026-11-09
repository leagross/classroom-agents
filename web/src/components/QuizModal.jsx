import { useEffect, useRef, useState } from "react";
import { fetchQuiz } from "../lib/api";
import renderMath from "../hooks/useMathRender";
import "./QuizModal.css";

export default function QuizModal({ open, sessionId, onClose }) {
  const [questions, setQuestions] = useState(null);
  const [answers, setAnswers] = useState({});
  const [graded, setGraded] = useState(false);
  const [error, setError] = useState("");
  const bodyRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    setQuestions(null);
    setAnswers({});
    setGraded(false);
    setError("");
    fetchQuiz(sessionId)
      .then(setQuestions)
      .catch((e) => setError(e.message));
  }, [open, sessionId]);

  useEffect(() => {
    if (questions && bodyRef.current) renderMath(bodyRef.current);
  }, [questions]);

  if (!open) return null;

  const score = questions
    ? questions.reduce((acc, q, i) => acc + (answers[i] === q.correct_index ? 1 : 0), 0)
    : 0;

  return (
    <div className="modal-overlay open" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal quiz-modal">
        <button className="modal-close" onClick={onClose}>✕</button>
        <h3>בוחן על השיעור</h3>
        <div className="quiz-body" ref={bodyRef}>
          {error && <p className="quiz-error">{error}</p>}
          {!error && !questions && <p>בונה בוחן על השיעור...</p>}
          {questions && questions.map((q, qi) => (
            <div className="quiz-question" key={qi}>
              <div className="q-text">{qi + 1}. {q.question}</div>
              {q.options.map((opt, oi) => {
                let cls = "quiz-option";
                if (answers[qi] === oi && !graded) cls += " selected";
                if (graded) {
                  if (oi === q.correct_index) cls += " correct";
                  else if (oi === answers[qi]) cls += " incorrect";
                }
                return (
                  <button
                    key={oi}
                    type="button"
                    className={cls}
                    disabled={graded}
                    onClick={() => setAnswers((a) => ({ ...a, [qi]: oi }))}
                  >
                    {opt}
                  </button>
                );
              })}
              {graded && <div className="quiz-explanation">{q.explanation}</div>}
            </div>
          ))}
          {questions && !graded && (
            <button className="btn btn-primary quiz-submit" onClick={() => setGraded(true)}>הגש בוחן</button>
          )}
          {graded && <div className="quiz-score">הציון שלך: {score} מתוך {questions.length}</div>}
        </div>
      </div>
    </div>
  );
}
