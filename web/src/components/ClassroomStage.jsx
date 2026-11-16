/**
 * The classroom's two-column stage: the conversation and the board, side by
 * side, with either one able to be the main surface.
 *
 * Why this is its own component: which of the two is centred is not a
 * property of the chat or of the board — it's a property of the room. The
 * board used to be stacked inside the chat column, which is why it ended up
 * squeezed into the middle of the page with nowhere to grow.
 *
 * focus="chat"  — the conversation is the main surface, the board sits
 *                 beside it, always visible and updating.
 * focus="board" — the board (or a presentation slide on it) takes the
 *                 centre and the conversation slides to a narrow column,
 *                 for when the class is watching rather than talking.
 */
export default function ClassroomStage({ focus = "chat", board, children }) {
  return (
    <div className={"stage" + (board ? "" : " no-board")} data-focus={board ? focus : "chat"}>
      <div className="stage-chat">{children}</div>
      {board && <div className="stage-board">{board}</div>}
    </div>
  );
}
