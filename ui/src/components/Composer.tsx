import { useEffect, useRef, useState } from "react";

export function Composer({ onSend, disabled, placeholder }: {
  onSend: (text: string) => boolean;
  disabled: boolean;
  placeholder: string;
}) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);

  useEffect(() => {
    if (!disabled) ref.current?.focus();
  }, [disabled]);

  const submit = () => {
    if (onSend(text)) setText("");
  };

  return (
    <form
      className="flex items-end gap-2 rounded-2xl border border-stone-300 bg-white p-2 shadow-sm focus-within:border-teal-600 dark:border-stone-700 dark:bg-stone-900"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <textarea
        ref={ref}
        rows={1}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder={placeholder}
        aria-label="Message"
        className="max-h-[200px] flex-1 resize-none bg-transparent px-2 py-1.5 outline-none placeholder:text-stone-400"
      />
      <button
        type="submit"
        disabled={disabled || !text.trim()}
        className="rounded-xl bg-teal-700 px-4 py-2 text-sm font-medium text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Send
      </button>
    </form>
  );
}
