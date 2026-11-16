import { useEffect } from "react";
// Styling (modal-overlay / modal / modal-close) already lives in theme.css —
// the four dialogs were sharing the class names all along, just not the markup.

/**
 * The shell every dialog in the app shares: backdrop, panel, close button,
 * click-outside and Escape to dismiss.
 *
 * All four dialogs already agreed on the same class names
 * (modal-overlay / modal / modal-close) — they just each re-implemented the
 * markup and the click-outside handler, and none of them handled Escape.
 * Closing on Escape now comes free to all of them.
 */
export default function Modal({ open, onClose, className = "", title, children }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === "Escape" && onClose?.();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="modal-overlay open"
      onClick={(e) => e.target === e.currentTarget && onClose?.()}
      role="presentation"
    >
      <div className={"modal " + className} role="dialog" aria-modal="true" aria-label={title}>
        <button className="modal-close" onClick={onClose} aria-label="סגור">
          ✕
        </button>
        {title && <h3>{title}</h3>}
        {children}
      </div>
    </div>
  );
}
