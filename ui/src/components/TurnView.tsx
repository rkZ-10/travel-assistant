import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Turn } from "../state";
import { Activity } from "./Activity";
import { FlightCardView } from "./FlightCardView";

function Meta({ meta, billed }: { meta: NonNullable<Turn["meta"]>; billed: boolean }) {
  const parts = [
    `${meta.tools.length} tool call${meta.tools.length === 1 ? "" : "s"}`,
    meta.turns != null && `${meta.turns} turns`,
    meta.durationMs != null && `${(meta.durationMs / 1000).toFixed(1)}s`,
    meta.costUsd != null &&
      (billed ? `~$${meta.costUsd.toFixed(3)} billed to the API key (est.)` : `~$${meta.costUsd.toFixed(3)} est., counts as plan usage`),
  ].filter(Boolean);
  return <div className="mt-3 font-mono text-xs text-stone-400">{parts.join(" · ")}</div>;
}

export function TurnView({ turn, onSend, billed = false }: { turn: Turn; onSend: (text: string) => void; billed?: boolean }) {
  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-teal-700 px-4 py-2.5 text-white">
          {turn.user}
        </div>
      </div>
      <div className="rounded-2xl rounded-bl-sm border border-stone-200 bg-white px-4 py-3 shadow-sm dark:border-stone-800 dark:bg-stone-900">
        <Activity steps={turn.steps} working={turn.status === "working"} />
        {turn.answer && (
          <div className="answer prose prose-stone max-w-none prose-p:my-2 prose-headings:mt-4 prose-headings:mb-2 dark:prose-invert">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{ a: (props) => <a {...props} target="_blank" rel="noreferrer" /> }}
            >
              {turn.answer}
            </ReactMarkdown>
          </div>
        )}
        {turn.cards && turn.cards.length > 0 && (
          <div className="mt-4 space-y-3">
            {turn.cards.map((c) => (
              <FlightCardView key={c.booking_token} card={c} onSearchAgain={onSend} />
            ))}
          </div>
        )}
        {turn.error && (
          <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
            {turn.error}
          </div>
        )}
        {turn.meta && <Meta meta={turn.meta} billed={billed} />}
      </div>
    </div>
  );
}
