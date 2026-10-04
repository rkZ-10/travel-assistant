import { useCallback, useEffect, useReducer, useRef } from "react";
import { initialState, isBusy, reducer, type ServerEvent } from "./state";

const RECONNECT_MS = 2000;
const KEY_STORE = "travel-assistant.api-key";

/** Only used when the user ticks "remember on this browser". Storage can be blocked: never throw. */
export const keyStore = {
  get: (): string | null => {
    try { return window.localStorage.getItem(KEY_STORE); } catch { return null; }
  },
  set: (key: string) => {
    try { window.localStorage.setItem(KEY_STORE, key); } catch { /* ignore */ }
  },
  clear: () => {
    try { window.localStorage.removeItem(KEY_STORE); } catch { /* ignore */ }
  },
};

function socketUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws`;
}

/** One WebSocket = one agent conversation on the backend. Reconnects if the server restarts. */
export function useAgent() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;

    const connect = () => {
      dispatch({ type: "connection", value: "connecting" });
      const ws = new WebSocket(socketUrl());
      wsRef.current = ws;
      let triedStored = false;
      ws.onmessage = (msg) => {
        const event = JSON.parse(msg.data) as ServerEvent;
        if (event.type === "ready" && event.auth) {
          if (event.auth.reason === "key_rejected") keyStore.clear();
          // A key remembered on this browser is sent once per connection when the server needs one.
          const stored = keyStore.get();
          if (event.auth.needs_key && event.auth.reason !== "key_rejected" && stored && !triedStored) {
            triedStored = true;
            ws.send(JSON.stringify({ type: "set_api_key", key: stored }));
          }
        }
        dispatch({ type: "server", event });
      };
      ws.onclose = () => {
        if (wsRef.current === ws) wsRef.current = null;
        if (stopped) return;
        dispatch({ type: "connection", value: "closed" });
        timer = window.setTimeout(connect, RECONNECT_MS);
      };
    };
    connect();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      wsRef.current?.close();
    };
  }, []);

  const send = useCallback(
    (text: string) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN || isBusy(state) || !text.trim()) return false;
      dispatch({ type: "user", text: text.trim() });
      ws.send(JSON.stringify({ type: "message", text: text.trim() }));
      return true;
    },
    [state],
  );

  const reset = useCallback(() => {
    wsRef.current?.send(JSON.stringify({ type: "reset" }));
    dispatch({ type: "reset" });
  }, []);

  const raw = (msg: object) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
  };

  /** Key goes to this browser session's agent only. `remember` also keeps it in localStorage. */
  const setApiKey = useCallback((key: string, remember: boolean) => {
    if (remember) keyStore.set(key.trim());
    else keyStore.clear();
    raw({ type: "set_api_key", key: key.trim() });
  }, []);

  /** Forget the typed key (and any remembered one); also used for "I've signed in again". */
  const clearApiKey = useCallback(() => {
    keyStore.clear();
    raw({ type: "clear_api_key" });
  }, []);

  return { state, send, reset, setApiKey, clearApiKey, busy: isBusy(state) };
}
