import type { Step } from "../state";

function Icon({ status }: { status: Step["status"] }) {
  if (status === "running")
    return <span className="inline-block size-3.5 animate-spin rounded-full border-2 border-teal-600 border-t-transparent" />;
  if (status === "done") return <span className="text-teal-600 dark:text-teal-400">✓</span>;
  if (status === "blocked") return <span className="text-amber-600 dark:text-amber-400">⊘</span>;
  return <span className="text-red-600 dark:text-red-400">✗</span>;
}

/** The agent's tool calls for one turn, updating live. */
export function Activity({ steps, working }: { steps: Step[]; working: boolean }) {
  if (steps.length === 0 && !working) return null;
  return (
    <ul className="mb-3 space-y-1.5 border-l-2 border-stone-200 pl-3 text-sm text-stone-600 dark:border-stone-700 dark:text-stone-400">
      {steps.map((s) => (
        <li key={s.id} className="flex items-start gap-2">
          <span className="mt-0.5 flex w-4 justify-center">
            <Icon status={s.status} />
          </span>
          <span className="flex-1">
            {s.label}
            {s.detail && <span className="block text-xs text-stone-500">{s.detail}</span>}
          </span>
          {s.durationMs != null && (
            <span className="font-mono text-xs tabular-nums text-stone-400">
              {s.durationMs < 1000 ? `${s.durationMs}ms` : `${(s.durationMs / 1000).toFixed(1)}s`}
            </span>
          )}
        </li>
      ))}
      {working && steps.every((s) => s.status !== "running") && (
        <li className="flex items-center gap-2 italic">
          <span className="flex w-4 justify-center">
            <span className="size-1.5 animate-pulse rounded-full bg-stone-400" />
          </span>
          Thinking…
        </li>
      )}
    </ul>
  );
}
