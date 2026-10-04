import { describe, expect, it } from "vitest";
import { toChanges } from "./components/PreferencesPanel";

const blank = { home_airport: null, preferred_airlines: null, max_stops: null, checked_bag: null, notes: null, max_price: 7000 };

describe("preferences form -> changes", () => {
  it("sets filled fields, clears emptied ones, skips unchanged", () => {
    const form = { home_airport: "hyd", preferred_airlines: "6e, ai", avoid_airlines: "", cabin: "", max_stops: "0",
      earliest_departure: "", latest_departure: "", seat: "", checked_bag: true, fare_flexibility: "", max_price: "",
      meal: "", notes: "Aisle near front\n" };
    expect(toChanges(form, blank)).toEqual({
      home_airport: "HYD", preferred_airlines: ["6E", "AI"], max_stops: 0, checked_bag: true,
      notes: ["Aisle near front"], clear: ["max_price"],
    });
  });

  it("airline chips and airport select produce the same codes the server stores", () => {
    const form = { home_airport: "BLR", preferred_airlines: "QP, 6E", avoid_airlines: "SG", cabin: "", max_stops: "",
      earliest_departure: "", latest_departure: "", seat: "", checked_bag: false, fare_flexibility: "", max_price: "7000",
      meal: "", notes: "" };
    expect(toChanges(form, blank)).toEqual({ home_airport: "BLR", preferred_airlines: ["QP", "6E"], avoid_airlines: ["SG"] });
  });
});
