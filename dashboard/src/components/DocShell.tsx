/**
 * The frame every Documentation page sits in — the same centred measure as a
 * console page, so a reference page is laid out like the rest of the app.
 * The distinction between "things you operate" and "things that explain" is
 * carried by the sidebar, not by pushing the content off to one side.
 */
export function DocShell({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto max-w-4xl px-8 py-10">{children}</div>
}
