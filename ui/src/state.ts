// Chat state as a pure reducer over server events, so it can be unit-tested without a socket.

export type StepStatus = "running" | "done" | "failed" | "blocked";

export interface Step {
  id: string;
  label: string;
  status: StepStatus;
  durationMs?: number | null;
  detail?: string;
}

export interface Segment {
  flight_number: string;
  airline: string;
  from_airport: string;
  to_airport: string;
  departs: string;
  arrives: string;
  duration_min: number;
}

export interface Itinerary {
  price: number | null;
  total_duration_min: number;
  stops: number;
  airlines: string[];
  segments: Segment[];
  notes?: string[];
}

export interface FlightCard {
  booking_token: string;
  label?: string | null;
  note?: string | null;
  itinerary: Itinerary;
  search: { origin: string; destination: string; date: string; return_date?: string | null };
  currency: string;
  fetched_at?: string | null;
  links_valid_minutes: number;
  source_url?: string | null;
}

export interface Turn {
  id: number;
  user: string;
  steps: Step[];
  cards?: FlightCard[];
  status: "working" | "done" | "error";
  answer?: string;
  error?: string;
  meta?: { turns?: number | null; costUsd?: number | null; durationMs?: number | null; tools: string[] };
}

export type Connection = "connecting" | "open" | "closed";

export interface ChatState {
  connection: Connection;
  model?: string;
  turns: Turn[];
}

export type ServerEvent =
  | { type: "ready"; model: string }
  | { type: "turn_start" }
  | { type: "tool_start"; id: string; tool: string; label: string }
  | { type: "tool_end"; id: string; tool: string; ok: boolean; duration_ms?: number | null; error?: string | null }
  | { type: "tool_blocked"; id: string; tool: string; label: string; reason: string }
  | { type: "answer"; text: string; turns?: number | null; cost_usd?: number | null; duration_ms?: number | null; tools: string[] }
  | { type: "flight_cards"; cards: FlightCard[] }
  | { type: "error"; message: string };

export type Action =
  | { type: "connection"; value: Connection }
  | { type: "user"; text: string }
  | { type: "reset" }
  | { type: "server"; event: ServerEvent };

export const initialState: ChatState = { connection: "connecting", turns: [] };

function updateLast(state: ChatState, fn: (t: Turn) => Turn): ChatState {
  if (state.turns.length === 0) return state;
  const turns = state.turns.slice();
  turns[turns.length - 1] = fn(turns[turns.length - 1]);
  return { ...state, turns };
}

export function reducer(state: ChatState, action: Action): ChatState {
  switch (action.type) {
    case "connection": {
      // A dropped connection ends whatever was in flight.
      const next = { ...state, connection: action.value };
      if (action.value !== "closed") return next;
      return updateLast(next, (t) =>
        t.status === "working" ? { ...t, status: "error", error: "Connection lost. Reconnecting…" } : t,
      );
    }
    case "user":
      return {
        ...state,
        turns: [...state.turns, { id: state.turns.length + 1, user: action.text, steps: [], status: "working" }],
      };
    case "reset":
      return { ...state, turns: [] };
    case "server":
      return applyEvent(state, action.event);
  }
}

function applyEvent(state: ChatState, e: ServerEvent): ChatState {
  switch (e.type) {
    case "ready":
      return { ...state, model: e.model, connection: "open" };
    case "turn_start":
      return state;
    case "tool_start":
      return updateLast(state, (t) => ({
        ...t,
        steps: [...t.steps, { id: e.id, label: e.label, status: "running" }],
      }));
    case "tool_end":
      return updateLast(state, (t) => ({
        ...t,
        steps: t.steps.map((s) =>
          s.id === e.id
            ? { ...s, status: e.ok ? "done" : "failed", durationMs: e.duration_ms, detail: e.error ?? undefined }
            : s,
        ),
      }));
    case "tool_blocked":
      return updateLast(state, (t) => ({
        ...t,
        steps: [...t.steps, { id: e.id, label: e.label, status: "blocked", detail: e.reason }],
      }));
    case "flight_cards":
      // A later call for the same itinerary replaces the earlier card (keeps its position).
      return updateLast(state, (t) => {
        const cards = [...(t.cards ?? [])];
        for (const c of e.cards) {
          const i = cards.findIndex((x) => x.booking_token === c.booking_token);
          if (i >= 0) cards[i] = c;
          else cards.push(c);
        }
        return { ...t, cards };
      });
    case "answer":
      return updateLast(state, (t) => ({
        ...t,
        status: "done",
        answer: e.text,
        steps: t.steps.map((s) => (s.status === "running" ? { ...s, status: "done" } : s)),
        meta: { turns: e.turns, costUsd: e.cost_usd, durationMs: e.duration_ms, tools: e.tools },
      }));
    case "error": {
      const last = state.turns[state.turns.length - 1];
      if (!last || last.status !== "working") return state; // e.g. a protocol error outside a turn
      return updateLast(state, (t) => ({ ...t, status: "error", error: e.message }));
    }
  }
}

export const isBusy = (s: ChatState) => s.turns.some((t) => t.status === "working");
