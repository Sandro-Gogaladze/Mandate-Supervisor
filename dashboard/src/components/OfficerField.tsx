import { UserRound } from 'lucide-react'
import { DEFAULT_OFFICER, useOfficer } from '@/lib/officer'

/**
 * Who is acting, in the header — the far right of the top bar, where an app
 * shell puts identity and where a reader looks for it.
 *
 * It lived in the sidebar footer, which reads as chrome: the one field whose
 * value is written onto every question asked, every rulebook promoted and
 * every decision signed sat below the navigation, where a first-time user
 * finds it after signing rather than before. It is an input, not a label, so
 * it looks like one on hover and focus and stays quiet otherwise.
 */
export function OfficerField() {
  const [officer, setOfficer] = useOfficer()
  return (
    <div className="flex items-center gap-1.5 rounded-md border border-transparent px-1.5 py-1 transition-colors hover:border-input focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/40">
      <UserRound className="size-3.5 shrink-0 text-muted-foreground" />
      <input
        value={officer}
        onChange={(e) => setOfficer(e.target.value)}
        onBlur={(e) => !e.target.value.trim() && setOfficer(DEFAULT_OFFICER)}
        placeholder={DEFAULT_OFFICER}
        aria-label="Acting as — recorded on every review you run and every decision you sign"
        title="Acting as — recorded on every review you run and every decision you sign"
        className="w-24 bg-transparent text-xs font-medium outline-none placeholder:text-muted-foreground/60 sm:w-36"
      />
    </div>
  )
}
