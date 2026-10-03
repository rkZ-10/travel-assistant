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
