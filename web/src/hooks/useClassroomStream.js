import { useCallback, useReducer, useRef } from "react";

/**
 * Turns the backend's SSE events into the conversation's state.
 *
 * This was an if/else chain inside ChatPanel that mutated four pieces of
 * state and two closure variables at once, and every new event type meant
 * another branch bolted onto it. As a reducer, each event is one case that
 * returns the next state, which is also why the half-finished message left
 * behind by an error can no longer leak into the next turn.
 *
 * The backend's event shape (start / token / end / board / done / error)
 * is the contract; see orchestrator.py.
 */

const initialState = {
  messages: [],
  streaming: null, // { name, color, text } — the reply currently arriving
  waiting: false, // request sent, nothing has come back yet
  teacherMode: null,
};

function reducer(state, action) {
  switch (action.type) {
    case "reset":
      return { ...initialState, messages: action.messages || [] };

    case "sent":
      return { ...state, waiting: true, messages: [...state.messages, action.message] };

    case "start":
      return {
        ...state,
        waiting: false,
        streaming: { name: action.name, color: action.color, text: "" },
      };

    case "token":
      if (!state.streaming) return state;
      return { ...state, streaming: { ...state.streaming, text: state.streaming.text + action.text } };

    case "end": {
      if (!state.streaming) return state;
      const finished = {
        agent: state.streaming.name,
        key: "assistant",
        color: state.streaming.color,
        text: state.streaming.text,
        isUser: false,
      };
      return { ...state, streaming: null, messages: [...state.messages, finished] };
    }

    case "done":
      return { ...state, waiting: false, teacherMode: action.teacherMode ?? state.teacherMode };

    case "error":
      // Drop the partial reply rather than leaving it on screen as if the
      // teacher had said it.
      return { ...state, streaming: null, waiting: false };

    default:
      return state;
  }
}

export default function useClassroomStream({ onBoardNotes, onSpoken, onApiKeyError } = {}) {
  const [state, dispatch] = useReducer(reducer, initialState);
  // Callbacks live in a ref so run() keeps a stable identity — otherwise
  // every render would hand useLessonAutoplay a new function and restart
  // its scheduling.
  const handlers = useRef({});
  handlers.current = { onBoardNotes, onSpoken, onApiKeyError };

  const reset = useCallback((messages) => dispatch({ type: "reset", messages }), []);

  const sent = useCallback((message) => dispatch({ type: "sent", message }), []);

  /** Drives one streaming call to completion; resolves with its done event. */
  const run = useCallback(async (callStreamFn) => {
    let doneEvent = null;
    let spoken = "";
    await callStreamFn((evt) => {
      switch (evt.type) {
        case "start":
          spoken = "";
          dispatch({ type: "start", name: evt.name, color: evt.color });
          break;
        case "token":
          spoken += evt.text;
          dispatch({ type: "token", text: evt.text });
          break;
        case "end":
          dispatch({ type: "end" });
          handlers.current.onSpoken?.(spoken);
          break;
        case "board":
          // Short notes the teacher chose to write — never the spoken text.
          handlers.current.onBoardNotes?.(evt.text);
          break;
        case "done":
          doneEvent = evt;
          dispatch({ type: "done", teacherMode: evt.teacher_mode });
          break;
        case "error":
          dispatch({ type: "error" });
          if (evt.detail?.includes("מפתח")) handlers.current.onApiKeyError?.(evt.detail);
          else alert(evt.detail || "שגיאה.");
          doneEvent = { type: "error" };
          break;
        default:
          break;
      }
    });
    return doneEvent;
  }, []);

  return { ...state, reset, sent, run };
}
