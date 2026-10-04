import { describe, expect, it } from "vitest";
import { initialState, isBusy, reducer, type Action, type ChatState } from "./state";

const run = (actions: Action[], start: ChatState = initialState) => actions.reduce(reducer, start);
const ev = (event: any): Action => ({ type: "server", event });

describe("chat reducer", () => {
  it("builds a turn from activity events and the answer", () => {
    const s = run([
      ev({ type: "ready", model: "sonnet" }),
      { type: "user", text: "HYD to MAA" },
      ev({ type: "turn_start" }),
      ev({ type: "tool_start", id: "t1", tool: "search_flights", label: "Searching flights" }),
      ev({ type: "tool_blocked", id: "t2", tool: "search_flights", label: "Searching again", reason: "limit" }),
      ev({ type: "tool_end", id: "t1", tool: "search_flights", ok: true, duration_ms: 2800 }),
      ev({ type: "answer", text: "Take IX 1831", turns: 4, cost_usd: 0.05, duration_ms: 9000, tools: ["search_flights"] }),
    ]);
    expect(s.model).toBe("sonnet");
    const t = s.turns[0];
    expect(t.status).toBe("done");
    expect(t.steps.map((x) => [x.id, x.status])).toEqual([["t1", "done"], ["t2", "blocked"]]);
    expect(t.steps[0].durationMs).toBe(2800);
    expect(t.answer).toBe("Take IX 1831");
    expect(isBusy(s)).toBe(false);
  });

  it("marks errors and lost connections on the working turn only", () => {
    const working = run([{ type: "user", text: "hi" }]);
    expect(isBusy(working)).toBe(true);
    expect(run([ev({ type: "error", message: "boom" })], working).turns[0].error).toBe("boom");
    const dropped = run([{ type: "connection", value: "closed" }], working);
    expect(dropped.turns[0].status).toBe("error");
    // an error outside a turn doesn't create or modify anything
    expect(run([ev({ type: "error", message: "x" })])).toEqual(initialState);
  });

  it("reset clears the conversation", () => {
    expect(run([{ type: "user", text: "a" }, { type: "reset" }]).turns).toEqual([]);
  });
});

describe("flight cards", () => {
  it("attaches cards to the working turn", () => {
    const card = { booking_token: "tok", itinerary: { price: 7069, total_duration_min: 80, stops: 0, airlines: ["IndiGo"], segments: [] },
      search: { origin: "HYD", destination: "MAA", date: "2026-10-17" }, currency: "INR", links_valid_minutes: 30 };
    const s = run([{ type: "user", text: "q" }, ev({ type: "flight_cards", cards: [card] })]);
    expect(s.turns[0].cards?.[0].booking_token).toBe("tok");
  });

  it("replaces a card shown twice instead of duplicating it", () => {
    const card = (tok: string, label: string) => ({ booking_token: tok, label,
      itinerary: { price: 1, total_duration_min: 80, stops: 0, airlines: ["IndiGo"], segments: [] },
      search: { origin: "HYD", destination: "MAA", date: "2026-10-17" }, currency: "INR", links_valid_minutes: 30 });
    const s = run([{ type: "user", text: "q" },
      ev({ type: "flight_cards", cards: [card("a", "Cheapest"), card("b", "Best timing")] }),
      ev({ type: "flight_cards", cards: [card("a", "Recommended"), card("c", "Flexible")] })]);
    expect(s.turns[0].cards?.map((c) => [c.booking_token, c.label])).toEqual(
      [["a", "Recommended"], ["b", "Best timing"], ["c", "Flexible"]]);
  });
});
