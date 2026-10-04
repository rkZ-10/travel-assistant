import { useEffect, useState } from "react";
import { api, type Preferences } from "../api";
import { AIRLINES, AIRPORTS } from "../india";

type Field =
  | { key: string; label: string; kind: "text"; placeholder?: string; upper?: boolean }
  | { key: string; label: string; kind: "list"; placeholder?: string; upper?: boolean }
  | { key: string; label: string; kind: "airport" }
  | { key: string; label: string; kind: "airlines"; other: string }
  | { key: string; label: string; kind: "select"; options: [string, string][] }
  | { key: string; label: string; kind: "number"; placeholder?: string }
  | { key: string; label: string; kind: "time" }
  | { key: string; label: string; kind: "bool" }
  | { key: string; label: string; kind: "lines"; placeholder?: string };

const FIELDS: Field[] = [
  { key: "home_airport", label: "Home airport", kind: "airport" },
  { key: "preferred_airlines", label: "Preferred airlines", kind: "airlines", other: "avoid_airlines" },
  { key: "avoid_airlines", label: "Avoid airlines", kind: "airlines", other: "preferred_airlines" },
  { key: "cabin", label: "Cabin", kind: "select", options: [["", "No preference"], ["economy", "Economy"], ["premium_economy", "Premium economy"], ["business", "Business"], ["first", "First"]] },
  { key: "max_stops", label: "Stops", kind: "select", options: [["", "Any"], ["0", "Nonstop only"], ["1", "Up to 1 stop"], ["2", "Up to 2 stops"]] },
  { key: "earliest_departure", label: "Earliest departure", kind: "time" },
  { key: "latest_departure", label: "Latest departure", kind: "time" },
  { key: "seat", label: "Seat", kind: "select", options: [["", "No preference"], ["window", "Window"], ["aisle", "Aisle"], ["any", "Any"]] },
  { key: "checked_bag", label: "Usually travel with a checked bag", kind: "bool" },
  { key: "fare_flexibility", label: "Fare flexibility", kind: "select", options: [["", "No preference"], ["cheapest", "Cheapest"], ["balanced", "Balanced"], ["flexible", "Flexible (low change/cancel fees)"]] },
  { key: "max_price", label: "Budget per one-way ticket (₹)", kind: "number", placeholder: "e.g. 7000" },
  { key: "meal", label: "Meal", kind: "text", placeholder: "e.g. vegetarian" },
  { key: "notes", label: "Notes (one per line)", kind: "lines", placeholder: "Anything else the assistant should know" },
];

type Form = Record<string, string | boolean>;

function toForm(p: Preferences): Form {
  const f: Form = {};
  for (const fd of FIELDS) {
    const v = p[fd.key];
    if (fd.kind === "bool") f[fd.key] = v === true;
    else if (fd.kind === "list" || fd.kind === "airlines") f[fd.key] = Array.isArray(v) ? v.join(", ") : "";
    else if (fd.kind === "lines") f[fd.key] = Array.isArray(v) ? v.join("\n") : "";
    else f[fd.key] = v == null ? "" : String(v);
  }
  return f;
}

/** Turn the form into {changes} for update_travel_preferences: set filled fields, clear emptied ones. */
export function toChanges(form: Form, original: Preferences): Record<string, unknown> {
  const changes: Record<string, unknown> = {};
  const clear: string[] = [];
  for (const fd of FIELDS) {
    const raw = form[fd.key];
    let value: unknown;
    if (fd.kind === "bool") value = raw ? true : null;
    else if (fd.kind === "list" || fd.kind === "airlines") value = String(raw).split(/[,\s]+/).map((x) => x.trim().toUpperCase()).filter(Boolean);
    else if (fd.kind === "lines") value = String(raw).split("\n").map((x) => x.trim()).filter(Boolean);
    else if (fd.kind === "number" || fd.key === "max_stops") value = raw === "" ? null : Number(raw);
    else value = String(raw).trim() === "" ? null : (fd.kind === "text" && fd.upper) || fd.kind === "airport" ? String(raw).trim().toUpperCase() : String(raw).trim();
    if (Array.isArray(value) && value.length === 0) value = null;

    const before = original[fd.key] ?? null;
    if (JSON.stringify(value) === JSON.stringify(before)) continue;
    if (value === null) clear.push(fd.key);
    else changes[fd.key] = value;
  }
  if (clear.length) changes.clear = clear;
  return changes;
}

const codes = (v: string | boolean | undefined) => String(v ?? "").split(/[,\s]+/).filter(Boolean);

/** Toggle chips for India-domestic airlines. A code picked here is removed from the opposite list. */
function AirlinePicker({ fd, form, setForm }: { fd: Extract<Field, { kind: "airlines" }>; form: Form; setForm: (f: Form) => void }) {
  const picked = codes(form[fd.key]);
  const extra = picked.filter((c) => !AIRLINES.some(([a]) => a === c)); // saved earlier via chat/CLI
  const toggle = (code: string) => {
    const on = picked.includes(code);
    const next = on ? picked.filter((c) => c !== code) : [...picked, code];
    setForm({ ...form, [fd.key]: next.join(", "), [fd.other]: codes(form[fd.other]).filter((c) => on || c !== code).join(", ") });
  };
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label={fd.label}>
      {[...AIRLINES, ...extra.map((c): [string, string] => [c, c])].map(([code, name]) => {
        const on = picked.includes(code);
        return (
          <button key={code} type="button" aria-pressed={on} onClick={() => toggle(code)} title={code}
            className={`rounded-full border px-2.5 py-1 text-xs ${on
              ? "border-teal-700 bg-teal-700 text-white"
              : "border-stone-300 text-stone-700 hover:border-teal-600 dark:border-stone-700 dark:text-stone-300"}`}>
            {name}
          </button>
        );
      })}
    </div>
  );
}

const input =
  "w-full rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-sm outline-none focus:border-teal-600 dark:border-stone-700 dark:bg-stone-900";

export function PreferencesPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [original, setOriginal] = useState<Preferences | null>(null);
  const [form, setForm] = useState<Form>({});
  const [status, setStatus] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setStatus(null);
    api.getPreferences().then(
      (p) => {
        setOriginal(p);
        setForm(toForm(p));
      },
      (e) => setStatus({ kind: "error", text: String(e.message ?? e) }),
    );
  }, [open]);

  if (!open) return null;
  const changes = original ? toChanges(form, original) : {};
  const dirty = Object.keys(changes).length > 0;

  const save = async () => {
    setSaving(true);
    setStatus(null);
    try {
      const r = await api.updatePreferences(changes);
      setOriginal(r.preferences);
      setForm(toForm(r.preferences));
      setStatus({ kind: "ok", text: r.message === "no changes" ? "Nothing to save." : `Saved: ${Object.keys(r.changed).join(", ")}` });
    } catch (e) {
      setStatus({ kind: "error", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-black/30" onClick={onClose}>
      <aside
        className="flex h-full w-full max-w-md flex-col bg-white shadow-xl dark:bg-stone-950"
        onClick={(e) => e.stopPropagation()}
        aria-label="Travel preferences"
      >
        <div className="flex items-center justify-between border-b border-stone-200 px-5 py-4 dark:border-stone-800">
          <div>
            <h2 className="font-semibold">Travel preferences</h2>
            <p className="text-xs text-stone-500">
              Used as defaults for every search. Shared with the CLI and Claude Desktop.
            </p>
          </div>
          <button onClick={onClose} className="text-xl text-stone-500 hover:text-stone-800" aria-label="Close">×</button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {!original && !status && <p className="text-sm text-stone-500">Loading…</p>}
          {original &&
            FIELDS.map((fd) => {
              // Chips are buttons: a <label> around them would toggle the first chip when its text is clicked.
              const Wrap = fd.kind === "airlines" ? "div" : "label";
              return (
              <Wrap key={fd.key} className="block text-sm">
                {fd.kind === "bool" ? (
                  <span className="flex items-center gap-2">
                    <input type="checkbox" checked={Boolean(form[fd.key])}
                      onChange={(e) => setForm({ ...form, [fd.key]: e.target.checked })} />
                    {fd.label}
                  </span>
                ) : (
                  <>
                    <span className="mb-1 block text-stone-600 dark:text-stone-400">{fd.label}</span>
                    {fd.kind === "airlines" ? (
                      <AirlinePicker fd={fd} form={form} setForm={setForm} />
                    ) : fd.kind === "airport" ? (
                      <select className={input} value={String(form[fd.key] ?? "")}
                        onChange={(e) => setForm({ ...form, [fd.key]: e.target.value })}>
                        <option value="">No home airport</option>
                        {form[fd.key] && !AIRPORTS.some(([c]) => c === form[fd.key]) && (
                          <option value={String(form[fd.key])}>{String(form[fd.key])}</option>
                        )}
                        {AIRPORTS.map(([c, city]) => <option key={c} value={c}>{city} ({c})</option>)}
                      </select>
                    ) : fd.kind === "select" ? (
                      <select className={input} value={String(form[fd.key] ?? "")}
                        onChange={(e) => setForm({ ...form, [fd.key]: e.target.value })}>
                        {fd.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                      </select>
                    ) : fd.kind === "lines" ? (
                      <textarea className={input} rows={3} placeholder={fd.placeholder} value={String(form[fd.key] ?? "")}
                        onChange={(e) => setForm({ ...form, [fd.key]: e.target.value })} />
                    ) : (
                      <input className={input} type={fd.kind === "number" ? "number" : fd.kind === "time" ? "time" : "text"}
                        placeholder={"placeholder" in fd ? fd.placeholder : undefined} value={String(form[fd.key] ?? "")}
                        onChange={(e) => setForm({ ...form, [fd.key]: e.target.value })} />
                    )}
                  </>
                )}
              </Wrap>
              );
            })}
        </div>
        <div className="border-t border-stone-200 px-5 py-3 dark:border-stone-800">
          {status && (
            <p className={`mb-2 text-sm ${status.kind === "ok" ? "text-teal-700 dark:text-teal-400" : "text-red-700 dark:text-red-400"}`}>
              {status.text}
            </p>
          )}
          <div className="flex items-center justify-between">
            <span className="text-xs text-stone-500">
              {original?.updated_at ? `Last saved ${new Date(String(original.updated_at)).toLocaleString()}` : "Nothing saved yet"}
            </span>
            <button onClick={save} disabled={!dirty || saving}
              className="rounded-lg bg-teal-700 px-4 py-1.5 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-40">
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
}
