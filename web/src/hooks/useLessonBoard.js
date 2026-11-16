/**
 * Binds BoardModel + ChalkWriter to React.
 *
 * The board's state used to live inside ChatPanel, which meant ChatPanel
 * had to mirror a paginator instance into its own useState and keep the two
 * in sync by hand. Now ChatPanel just calls board.write(text) when a board
 * event arrives, and reads board.pages / board.pageIndex for rendering.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import BoardModel from "../lib/board/BoardModel";
import ChalkWriter from "../lib/board/ChalkWriter";

export default function useLessonBoard({ sessionId } = {}) {
  const modelRef = useRef(null);
  if (!modelRef.current) modelRef.current = new BoardModel();

  const [pages, setPages] = useState([[]]);
  const [pageIndex, setPageIndex] = useState(0);
  // The entry currently being "handwritten", and how much of it is visible.
  const [writing, setWriting] = useState(null); // { id, revealed }
  const queueRef = useRef([]);

  const writerRef = useRef(null);

  const publish = useCallback(() => {
    setPages(modelRef.current.pages.map((page) => [...page]));
  }, []);

  /** Animate the queued entries one after another, so a 4-line block is
   *  written line by line instead of appearing all at once. */
  const drainQueue = useCallback(() => {
    const next = queueRef.current.shift();
    if (!next) {
      setWriting(null);
      return;
    }
    setWriting({ id: next.id, revealed: "" });
    writerRef.current.write(next.text);
  }, []);

  if (!writerRef.current) {
    writerRef.current = new ChalkWriter({
      onUpdate: (revealed) => setWriting((prev) => (prev ? { ...prev, revealed } : prev)),
      onDone: () => drainQueue(),
    });
  }

  const write = useCallback(
    (text) => {
      const { pageIndex: target, entries } = modelRef.current.write(text);
      if (!entries.length) return;
      publish();
      // Follow the teacher to the page being written on, the way a class
      // looks at whichever board surface is in use.
      setPageIndex(target);
      queueRef.current.push(...entries);
      if (!writerRef.current.isWriting) drainQueue();
    },
    [drainQueue, publish]
  );

  const reset = useCallback(() => {
    writerRef.current.stop();
    queueRef.current = [];
    setWriting(null);
    modelRef.current.reset();
    publish();
    setPageIndex(0);
  }, [publish]);

  useEffect(() => {
    reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  useEffect(() => () => writerRef.current.stop(), []);

  const goTo = useCallback(
    (index) => {
      const clamped = Math.max(0, Math.min(modelRef.current.lastPageIndex, index));
      // Jumping away from the page being written would leave it half
      // finished forever, so finish it first.
      if (clamped !== pageIndex) writerRef.current.skip();
      setPageIndex(clamped);
    },
    [pageIndex]
  );

  return useMemo(
    () => ({
      pages,
      pageIndex,
      pageCount: pages.length,
      writing,
      write,
      reset,
      goTo,
      prev: () => goTo(pageIndex - 1),
      next: () => goTo(pageIndex + 1),
      skipAnimation: () => writerRef.current.skip(),
      pagesText: () => modelRef.current.allPagesText(),
      isEmpty: modelRef.current.isEmpty(),
    }),
    [pages, pageIndex, writing, write, reset, goTo]
  );
}
