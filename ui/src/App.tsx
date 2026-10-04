import { useEffect, useRef, useState } from "react";
import { AuthBadge, AuthPanel, KeyNeeded } from "./components/Auth";
import { Composer } from "./components/Composer";
import { PreferencesPanel } from "./components/PreferencesPanel";
import { TurnView } from "./components/TurnView";
import { Welcome } from "./components/Welcome";
import { useAgent } from "./useAgent";

const STATUS = {
  open: { dot: "bg-teal-500", text: "Connected" },
  connecting: { dot: "bg-amber-400 animate-pulse", text: "Connecting…" },
  closed: { dot: "bg-red-500", text: "Disconnected, retrying…" },
} as const;

export default function App() {
  const { state, send, reset, setApiKey, clearApiKey, busy } = useAgent();
  const bottom = useRef<HTMLDivElement>(null);
  const status = STATUS[state.connection];
  const needsKey = Boolean(state.auth?.needs_key);
  const canSend = state.connection === "open" && !busy && !needsKey;
  const [prefsOpen, setPrefsOpen] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const billed = state.auth?.mode === "browser_key" || state.auth?.mode === "server_key";
  const keyCard = needsKey && state.auth && (
    <KeyNeeded auth={state.auth} error={state.authError} onKey={setApiKey} onRetryLogin={clearApiKey} />
  );

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [state.turns]);

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex items-center justify-between border-b border-stone-200 bg-white/80 px-4 py-3 backdrop-blur dark:border-stone-800 dark:bg-stone-950/80">
        <div className="flex items-center gap-3">
          <span className="whitespace-nowrap text-lg font-semibold tracking-tight">Travel Assistant</span>
          {state.model && (
            <span className="hidden rounded-full bg-stone-100 px-2 py-0.5 font-mono text-xs sm:inline text-stone-600 dark:bg-stone-800 dark:text-stone-300">
              {state.model}
            </span>
          )}
        </div>
        <div className="flex items-center gap-4 text-sm">
          <AuthBadge auth={state.auth} onClick={() => setAuthOpen(true)} />
          <span className="flex items-center gap-1.5 text-stone-500">
            <span className={`size-2 rounded-full ${status.dot}`} title={status.text} />
            <span className="hidden sm:inline">{status.text}</span>
          </span>
          <button
            onClick={() => setPrefsOpen(true)}
            className="whitespace-nowrap rounded-lg border border-stone-300 px-3 py-1 text-stone-700 transition hover:bg-stone-100 dark:border-stone-700 dark:text-stone-300 dark:hover:bg-stone-800"
          >
            Preferences
          </button>
          <button
            onClick={reset}
            disabled={busy || state.turns.length === 0}
            className="whitespace-nowrap rounded-lg border border-stone-300 px-3 py-1 text-stone-700 transition hover:bg-stone-100 disabled:opacity-40 dark:border-stone-700 dark:text-stone-300 dark:hover:bg-stone-800"
          >
            New chat
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto px-4">
        <div className="mx-auto max-w-3xl space-y-6 py-6">
          {state.turns.length === 0 && keyCard}
          {state.turns.length === 0 ? (
            <Welcome onPick={(t) => send(t)} disabled={!canSend} />
          ) : (
            state.turns.map((t) => <TurnView key={t.id} turn={t} billed={billed} onSend={(text) => send(text)} />)
          )}
          {state.turns.length > 0 && keyCard}
          <div ref={bottom} />
        </div>
      </main>

      <footer className="px-4 pb-4">
        <div className="mx-auto max-w-3xl">
          <Composer
            onSend={send}
            disabled={!canSend}
            placeholder={busy ? "Working on it…" : needsKey ? "Add an API key above to start" : "Ask about flights, fares, baggage or refunds"}
          />
          <p className="mt-2 text-center text-xs text-stone-400">
            Fares and policies come from tools, with sources and dates. Booking happens on the
            airline's or travel site's own page.
          </p>
        </div>
      </footer>
      <PreferencesPanel open={prefsOpen} onClose={() => setPrefsOpen(false)} />
      <AuthPanel open={authOpen} onClose={() => setAuthOpen(false)} auth={state.auth} error={state.authError}
        onKey={setApiKey} onForget={clearApiKey} />
    </div>
  );
}
