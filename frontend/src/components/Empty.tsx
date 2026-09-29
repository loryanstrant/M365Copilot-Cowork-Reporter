/**
 * The "there is nothing here" placeholder, shown inside a card.
 *
 * Lifted out of the deleted Card.tsx, which is where it used to live alongside
 * a bespoke card that was invisible in dark mode. The background is
 * `dark:bg-slate-800/60` rather than the old `dark:bg-slate-900`: it sits
 * *inside* a `.card` (slate-800), so a slate-900 fill made the empty state
 * darker than the surface holding it, which read as a hole rather than a
 * placeholder.
 */
export default function Empty({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-10 text-center text-sm text-slate-500 dark:border-slate-600 dark:bg-slate-800/60 dark:text-slate-400">
      {message}
    </div>
  );
}
