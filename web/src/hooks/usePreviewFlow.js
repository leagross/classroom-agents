import { useCallback, useState } from "react";

/**
 * The generate → review → approve / regenerate / cancel flow, once.
 *
 * Three components ran their own copy of this (the lesson plan in
 * SetupForm, the outline in SyllabusBuilder, and a lesson's plan in
 * SyllabusView), each with its own preview / loading / error triple and
 * its own try/finally. They behaved subtly differently — only some of
 * them cleared the previous error before retrying, and only some disabled
 * the button while a second request was in flight.
 *
 * `generate` is the async call that produces whatever is being previewed.
 * Everything else — what it looks like, and what approving it does — stays
 * in the component, since that genuinely differs between the three.
 */
export default function usePreviewFlow(generate, { onError } = {}) {
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const run = useCallback(
    async (...args) => {
      setError("");
      setLoading(true);
      try {
        const result = await generate(...args);
        setPreview(result);
        return result;
      } catch (e) {
        const message = e?.message || "משהו השתבש. נסה שוב.";
        setError(message);
        onError?.(e);
        return null;
      } finally {
        setLoading(false);
      }
    },
    [generate, onError]
  );

  const cancel = useCallback(() => {
    setPreview(null);
    setError("");
  }, []);

  /** For the approve step, which is also async and also needs the spinner
   *  and the error line — without it each caller re-invents them. */
  const submit = useCallback(
    async (action) => {
      setError("");
      setLoading(true);
      try {
        return await action();
      } catch (e) {
        setError(e?.message || "משהו השתבש. נסה שוב.");
        onError?.(e);
        return null;
      } finally {
        setLoading(false);
      }
    },
    [onError]
  );

  return { preview, setPreview, loading, error, setError, run, cancel, submit };
}
