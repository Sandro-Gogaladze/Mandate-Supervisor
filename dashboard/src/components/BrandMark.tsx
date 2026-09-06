/**
 * The brand mark — the payment card with the agent's face on it, the thing
 * this console supervises. Vector, and geometrically identical to
 * `dashboard/public/mark.svg`, which is the favicon and app icon.
 *
 * Everything here is tuned for legibility small, where the mark actually has
 * to work: a full-bleed rounded tile rather than a disc (the glyph is wider
 * than it is tall, so a circle would spend the canvas on empty corners), the
 * drawing scaled out to a narrow margin, and strokes set far heavier than the
 * logo's — a hairline disappears in a browser tab.
 *
 * The tile takes `--sidebar`, so on the rail it dissolves into the rail and
 * reads as the glyph alone, and it re-matches on its own when the theme flips.
 * The published `mark.svg` hardcodes the light-theme value of that token.
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 1254 1254" className={className} role="img" aria-label="Mandate Supervisor">
      <rect width="1254" height="1254" rx="200" fill="var(--sidebar)" />
      <g transform="translate(-49.5 -49.4) scale(1.079)" fill="#fff">
        {/* The card outline breaks at the top so the agent's antenna passes
            through it, exactly as in the logo. */}
        <path
          d="M767.5 403.5H1024a124.5 124.5 0 0 1 124.5 124.5v354a124.5 124.5 0 0 1-124.5 124.5H230A124.5 124.5 0 0 1 105.5 882V528A124.5 124.5 0 0 1 230 403.5h396.5"
          fill="none"
          stroke="#fff"
          strokeWidth="71"
          strokeLinecap="round"
        />
        <rect x="175" y="635" width="93" height="86" rx="18" />
        <rect x="280" y="635" width="92" height="86" rx="18" />
        <rect x="175" y="733" width="93" height="83" rx="18" />
        <rect x="280" y="733" width="92" height="83" rx="18" />
        <rect x="660" y="300" width="75" height="290" rx="37.5" />
        <circle cx="697.5" cy="319" r="111" />
        <rect x="434.5" y="555.5" width="562" height="331" rx="165.5" fill="none" stroke="#fff" strokeWidth="67" />
        <circle cx="590" cy="721" r="57" />
        <circle cx="836" cy="721" r="57" />
      </g>
    </svg>
  )
}
