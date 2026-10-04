import { useState } from "react";
import type { Auth } from "../state";

const SHORT: Record<Auth["mode"], string> = {
  claude_login: "Claude login",
  browser_key: "Your API key",
  server_key: "API key (.env)",
  none: "Not signed in",
};

export function AuthBadge({ auth, onClick }: { auth?: Auth; onClick: () => void }) {
  if (!auth) return null;
  const warn = auth.mode === "none";
  return (
    <button
      onClick={onClick}
      title={auth.label}
      className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs ${warn
        ? "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200"
        : "bg-stone-100 text-stone-600 hover:bg-stone-200 dark:bg-stone-800 dark:text-stone-300 dark:hover:bg-stone-700"}`}
    >
      {SHORT[auth.mode]}
    </button>
  );
}

const input =
  "w-full rounded-lg border border-stone-300 bg-white px-3 py-1.5 font-mono text-sm outline-none focus:border-teal-600 dark:border-stone-700 dark:bg-stone-900";

/** Enter an Anthropic API key. It is sent to this browser session's agent only. */
export function ApiKeyForm({ onSubmit, error }: { onSubmit: (key: string, remember: boolean) => void; error?: string }) {
  const [key, setKey] = useState("");
  const [remember, setRemember] = useState(false);
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (key.trim()) onSubmit(key, remember);
        setKey("");
      }}
    >
      <input
        className={input}
        type="password"
        autoComplete="off"
        spellCheck={false}
        placeholder="sk-ant-..."
        aria-label="Anthropic API key"
        value={key}
        onChange={(e) => setKey(e.target.value)}
      />
      {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}
      <label className="flex items-center gap-2 text-xs text-stone-600 dark:text-stone-400">
        <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
        Remember on this browser (stored in this browser only; skip on a shared computer)
      </label>
      <div className="flex items-center justify-between gap-3">
        <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer"
          className="text-xs text-teal-800 underline dark:text-teal-300">
          Get a key from the Anthropic Console
        </a>
        <button type="submit" disabled={!key.trim()}
          className="rounded-lg bg-teal-700 px-4 py-1.5 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-40">
          Use this key
        </button>
      </div>
      <p className="text-xs text-stone-500">
        Usage is billed to your Anthropic account (pay as you go). The key is kept in memory for this
        chat session only and is never written to disk or logs by the app.
      </p>
    </form>
  );
}

function LoginExpired({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="space-y-2 text-sm">
      <p>Your Claude login has expired. To keep using your subscription:</p>
      <ol className="list-decimal space-y-1 pl-5 text-stone-700 dark:text-stone-300">
        <li>Open a terminal and run <code>claude</code></li>
        <li>Type <code>/login</code> and finish signing in in the browser, then <code>/exit</code></li>
      </ol>
      <button onClick={onRetry} className="rounded-lg border border-teal-700 px-3 py-1 text-sm text-teal-800 hover:bg-teal-50 dark:text-teal-300 dark:hover:bg-teal-950">
        I've signed in again
      </button>
      <p className="pt-1 text-stone-600 dark:text-stone-400">Or use an API key instead:</p>
    </div>
  );
}

/** Inline card shown in the chat when the agent can't run until a key is added. */
export function KeyNeeded({ auth, error, onKey, onRetryLogin }: {
  auth: Auth; error?: string; onKey: (key: string, remember: boolean) => void; onRetryLogin: () => void;
}) {
  return (
    <div className="rounded-2xl border border-amber-300 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/40">
      <h2 className="mb-2 font-semibold">
        {auth.reason === "login_expired" ? "Sign in again or use an API key" : "Add an Anthropic API key to start"}
      </h2>
      {auth.reason === "login_expired" ? (
        <LoginExpired onRetry={onRetryLogin} />
      ) : (
        <p className="mb-2 text-sm text-stone-700 dark:text-stone-300">
          {auth.reason === "key_only"
            ? "This copy of the assistant runs on visitors' own API keys."
            : auth.reason === "key_rejected"
              ? "Anthropic rejected the last key."
              : "No Claude login was found on this computer. Sign in with Claude Code (run claude, then /login) and reload, or use an API key."}
        </p>
      )}
      <ApiKeyForm onSubmit={onKey} error={error} />
    </div>
  );
}

/** Opened from the header badge: shows what the agent runs on and lets you switch. */
export function AuthPanel({ open, onClose, auth, error, onKey, onForget }: {
  open: boolean; onClose: () => void; auth?: Auth; error?: string;
  onKey: (key: string, remember: boolean) => void; onForget: () => void;
}) {
  const [showForm, setShowForm] = useState(false);
  if (!open || !auth) return null;
  return (
    <div className="fixed inset-0 z-20 flex items-start justify-center bg-black/30 p-4 pt-20" onClick={onClose}>
      <div className="w-full max-w-md space-y-3 rounded-2xl bg-white p-5 shadow-xl dark:bg-stone-950"
        onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Claude access">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Claude access</h2>
          <button onClick={onClose} className="text-xl text-stone-500 hover:text-stone-800" aria-label="Close">×</button>
        </div>
        <p className="text-sm">{auth.label}.</p>
        {auth.mode === "claude_login" && (
          <p className="text-sm text-stone-600 dark:text-stone-400">
            Detected on this computer, so chats count against your Claude plan. Nothing to set up.
          </p>
        )}
        {auth.mode === "server_key" && (
          <p className="text-sm text-stone-600 dark:text-stone-400">Set in the server's .env; usage is billed to that key.</p>
        )}
        {auth.mode === "browser_key" ? (
          <button onClick={() => { onForget(); setShowForm(false); }}
            className="rounded-lg border border-stone-300 px-3 py-1 text-sm hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800">
            Forget my key
          </button>
        ) : auth.needs_key || showForm ? (
          <ApiKeyForm onSubmit={(k, r) => { onKey(k, r); setShowForm(false); }} error={error} />
        ) : (
          <button onClick={() => setShowForm(true)} className="text-sm text-teal-800 underline dark:text-teal-300">
            Use an API key instead
          </button>
        )}
      </div>
    </div>
  );
}
