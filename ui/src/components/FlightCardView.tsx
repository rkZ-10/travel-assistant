import { useState } from "react";
import { api, openBooking, type BookingOptions } from "../api";
import type { FlightCard } from "../state";
import { clock, duration, hhmm, inr, useMinutesLeft } from "../time";

function Expiry({ minutesLeft, fetchedAt, what }: { minutesLeft: number | null; fetchedAt?: string | null; what: string }) {
  if (minutesLeft == null) return null;
  if (minutesLeft < 0)
    return <span className="text-red-700 dark:text-red-400">{what} expired (fetched {clock(fetchedAt)})</span>;
  return (
    <span className={minutesLeft <= 5 ? "text-amber-700 dark:text-amber-400" : ""}>
      {what} valid for about {Math.max(minutesLeft, 1)} more min (fetched {clock(fetchedAt)})
    </span>
  );
}

const SHOWN = 5;

function Options({ data, onRefresh, loading }: { data: BookingOptions; onRefresh: () => void; loading: boolean }) {
  const left = useMinutesLeft(data.fetched_at, data.links_valid_minutes);
  const expired = left != null && left < 0;
  const [all, setAll] = useState(false);
  const hidden = Math.max(data.options.length - SHOWN, 0);
  const shown = all ? data.options : data.options.slice(0, SHOWN);
  return (
    <div className="mt-3 space-y-2 border-t border-stone-200 pt-3 dark:border-stone-800">
      {data.notes.map((n) => (
        <p key={n} className="text-xs text-amber-700 dark:text-amber-400">{n}</p>
      ))}
      {shown.map((o, i) => (
        <div key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-stone-50 px-3 py-2 text-sm dark:bg-stone-800/60">
          <span className="font-medium">{o.seller}</span>
          {o.is_airline && (
            <span className="rounded bg-teal-100 px-1.5 text-xs text-teal-800 dark:bg-teal-900 dark:text-teal-200">airline direct</span>
          )}
          {o.fare_name && <span className="text-stone-600 dark:text-stone-300">{o.fare_name}</span>}
          {o.leg !== "together" && <span className="text-xs text-stone-500">{o.leg}</span>}
          <span className="ml-auto font-mono tabular-nums">{inr(o.price)}</span>
          {o.booking_url && o.booking_post_data ? (
            <button
              disabled={expired}
              onClick={() => openBooking(o.booking_url!, o.booking_post_data!)}
              className="rounded-lg bg-teal-700 px-3 py-1 text-xs font-medium text-white hover:bg-teal-800 disabled:opacity-40"
            >
              Book on {o.seller} ↗
            </button>
          ) : o.booking_phone ? (
            <span className="text-xs">Call {o.booking_phone}</span>
          ) : null}
          {o.features.length > 0 && <span className="w-full text-xs text-stone-500">{o.features.join(" · ")}</span>}
        </div>
      ))}
      {hidden > 0 && (
        <button onClick={() => setAll(!all)} className="text-xs text-teal-800 underline hover:text-teal-900 dark:text-teal-300">
          {all ? "Show fewer sellers" : `Show ${hidden} more seller${hidden === 1 ? "" : "s"}`}
        </button>
      )}
      <div className="flex items-center justify-between text-xs text-stone-500">
        <Expiry minutesLeft={left} fetchedAt={data.fetched_at} what="These links are" />
        {expired && (
          <button onClick={onRefresh} disabled={loading} className="underline hover:text-teal-700">
            Refresh options
          </button>
        )}
      </div>
      <p className="text-xs text-stone-500">
        Opens the seller's site with this flight selected. Price and seats are confirmed there. You pay the seller directly.
      </p>
    </div>
  );
}

export function FlightCardView({ card, onSearchAgain }: { card: FlightCard; onSearchAgain: (text: string) => void }) {
  const [options, setOptions] = useState<BookingOptions | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const left = useMinutesLeft(card.fetched_at, card.links_valid_minutes);
  const expired = left != null && left < 0;
  const it = card.itinerary;
  const first = it.segments[0];
  const last = it.segments[it.segments.length - 1];
  const s = card.search;

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setOptions(await api.bookingOptions({ booking_token: card.booking_token, origin: s.origin, destination: s.destination,
        date: s.date, return_date: s.return_date }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-stone-200 p-4 dark:border-stone-700">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        {card.label && (
          <span className="rounded-full bg-teal-50 px-2 py-0.5 text-xs font-medium text-teal-800 dark:bg-teal-950 dark:text-teal-200">
            {card.label}
          </span>
        )}
        <span className="font-medium">{it.airlines.join(" + ")}</span>
        <span className="font-mono text-sm text-stone-500">{it.segments.map((x) => x.flight_number).join(" · ")}</span>
        <span className="ml-auto text-lg font-semibold tabular-nums">{inr(it.price)}</span>
      </div>
      {first && last && (
        <div className="mt-1 text-sm text-stone-600 dark:text-stone-300">
          {first.from_airport} {hhmm(first.departs)} → {last.to_airport} {hhmm(last.arrives)} · {duration(it.total_duration_min)} ·{" "}
          {it.stops === 0 ? "nonstop" : `${it.stops} stop${it.stops > 1 ? "s" : ""}`} · {s.date}
          {s.return_date ? ` (return ${s.return_date})` : ""}
        </div>
      )}
      {card.note && <p className="mt-2 text-sm text-stone-700 dark:text-stone-300">{card.note}</p>}

      <div className="mt-3 flex flex-wrap items-center gap-3">
        {!options && (
          <button
            onClick={load}
            disabled={loading || expired}
            className="rounded-lg border border-teal-700 px-3 py-1.5 text-sm font-medium text-teal-800 hover:bg-teal-50 disabled:opacity-40 dark:text-teal-300 dark:hover:bg-teal-950"
          >
            {loading ? "Finding sellers…" : "See booking options"}
          </button>
        )}
        {expired && (
          <button
            onClick={() => onSearchAgain(`Search again: ${s.origin} to ${s.destination} on ${s.date}${s.return_date ? `, returning ${s.return_date}` : ""}`)}
            className="rounded-lg bg-teal-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-teal-800"
          >
            Search again
          </button>
        )}
        {card.source_url && (
          <a href={card.source_url} target="_blank" rel="noreferrer" className="text-sm text-stone-500 underline hover:text-teal-700">
            Google Flights
          </a>
        )}
        <span className="ml-auto text-xs text-stone-500">
          <Expiry minutesLeft={left} fetchedAt={card.fetched_at} what="Fares" />
        </span>
      </div>
      {!options && !expired && (
        <p className="mt-1 text-xs text-stone-400">Checking sellers uses 1 search from your monthly SerpApi quota.</p>
      )}
      {error && <p className="mt-2 text-sm text-red-700 dark:text-red-400">{error}</p>}
      {options && <Options data={options} onRefresh={load} loading={loading} />}
    </div>
  );
}
