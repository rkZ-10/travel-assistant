import { useCallback, useEffect, useReducer, useRef } from "react";
import { initialState, isBusy, reducer, type ServerEvent } from "./state";

const RECONNECT_MS = 2000;

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
      ws.onmessage = (msg) => dispatch({ type: "server", event: JSON.parse(msg.data) as ServerEvent });
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

  return { state, send, reset, busy: isBusy(state) };
}
