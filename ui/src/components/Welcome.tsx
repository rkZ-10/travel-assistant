const STARTERS = [
  "Cheapest nonstop Hyderabad to Chennai next Friday, and what would cancelling cost?",
  "How much checked baggage do I get on Akasa Air?",
  "IndiGo denied me boarding and rebooked me 5 hours later. What compensation am I owed?",
  "Round trip Delhi to Mumbai, leaving in two weeks and back four days later.",
];

export function Welcome({ onPick, disabled }: { onPick: (text: string) => void; disabled: boolean }) {
  return (
    <div className="mx-auto max-w-2xl py-16 text-center">
      <div className="text-4xl">✈️</div>
      <h1 className="mt-3 text-2xl font-semibold tracking-tight">Where are you flying?</h1>
      <p className="mt-2 text-stone-500">
        Live fares for Indian domestic routes, airline fare rules and DGCA passenger rights, with sources.
      </p>
      <div className="mt-8 grid gap-2 text-left sm:grid-cols-2">
        {STARTERS.map((s) => (
          <button
            key={s}
            disabled={disabled}
            onClick={() => onPick(s)}
            className="rounded-xl border border-stone-200 bg-white px-4 py-3 text-left text-sm text-stone-700 transition hover:border-teal-600 hover:text-teal-800 disabled:opacity-50 dark:border-stone-800 dark:bg-stone-900 dark:text-stone-300 dark:hover:text-teal-300"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
