/**
 * The drafting-table texture: a fine grid in the logo blue, fading out so
 * it never competes with the type sitting on it.
 *
 * Used only on surfaces where something is being *explained* — the hero,
 * the review rail, the specialist fan. Live data surfaces (the queue,
 * recent cases, findings) stay plain: behind real records the same texture
 * reads as noise rather than as paper, and using it everywhere would spend
 * the one bit of brand texture this console has.
 *
 * `strength` is the grid line's share of the brand blue; the hero takes
 * the full weight, nested cards sit lighter so the page keeps a hierarchy.
 */
export function BlueprintGrid({
  strength = 7,
  size = 28,
  fade = 'bottom',
}: {
  strength?: number
  size?: number
  /** Where the grid dissolves: down the card, or outward from the centre. */
  fade?: 'bottom' | 'radial'
}) {
  const line = `color-mix(in oklab, var(--brand-blue) ${strength}%, transparent)`
  const mask =
    fade === 'radial'
      ? 'radial-gradient(ellipse at center, black 62%, transparent 96%)'
      : 'linear-gradient(to bottom, black 30%, transparent 95%)'
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0"
      style={{
        backgroundImage: `linear-gradient(${line} 1px, transparent 1px), linear-gradient(90deg, ${line} 1px, transparent 1px)`,
        backgroundSize: `${size}px ${size}px`,
        maskImage: mask,
        WebkitMaskImage: mask,
      }}
    />
  )
}
