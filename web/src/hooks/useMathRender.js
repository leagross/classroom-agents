/** Renders LaTeX ($...$, $$...$$) inside a DOM element via KaTeX's auto-render,
 * loaded globally from index.html. Call after an element's final text is set —
 * not on every streaming token, to avoid rendering unbalanced mid-stream LaTeX. */
export default function renderMath(el) {
  if (!el || typeof window.renderMathInElement !== "function") return;
  try {
    window.renderMathInElement(el, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\(", right: "\\)", display: false },
      ],
      throwOnError: false,
    });
  } catch (e) { /* malformed LaTeX from the model shouldn't break the chat */ }
}
