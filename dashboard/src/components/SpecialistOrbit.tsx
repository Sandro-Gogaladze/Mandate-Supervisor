import { nodeMeta, SPECIALISTS, AGENT_ICON } from '@/lib/node-meta'
import { BrandMark } from '@/components/BrandMark'
import { cn } from '@/lib/utils'

/**
 * What each specialist checks, in three or four words. The blurbs in
 * node-meta are full sentences — too long to sit on a spoke, and the
 * per-agent pages carry the detail anyway. This is the label, not the
 * explanation.
 */
const CHECKS: Record<string, string> = {
  mandate: 'Scope, caps, chain',
  kya: 'Identity and delegation',
  provenance: 'Declared vs observed',
  injection: 'Hidden instructions',
  counterparty: 'Who was really paid',
  consent: 'What the human saw',
  log: 'Patterns across payments',
  drift: 'Change over time',
  control_assurance: 'Whether controls fired',
  systemic: 'Links across institutions',
}

/**
 * Layout is a fan, not a ring. A circle cannot seat ten *labelled*
 * nodes: near the poles consecutive spokes converge faster than a two-line
 * label is tall, so the top three collide however far the radius is
 * pushed. Two flanking columns keep every label horizontal and provably
 * clear of its neighbours.
 */
// Height tracks the tallest column, not a fixed guess: five rows of 78 plus
// the roundel and a margin. At 470 (sized for six rows) the card carried an
// empty band above and below the fan.
const BOX = { w: 900, h: 400 }
const HUB = { x: BOX.w / 2, y: BOX.h / 2, w: 208 }
const COL = { left: 296, right: BOX.w - 296 }
const ROW_GAP = 78

/** Split down the middle, derived rather than typed: the roster has changed
 *  size twice, and a hardcoded split silently leaves one column longer than
 *  the other the next time it does. An odd roster puts the extra seat left. */
const SPLIT = Math.ceil(SPECIALISTS.length / 2)

function seat(i: number) {
  const left = i < SPLIT
  const n = left ? SPLIT : SPECIALISTS.length - SPLIT
  const k = left ? i : i - SPLIT
  // Each column is centred on the hub's own centre line.
  const y = HUB.y + (k - (n - 1) / 2) * ROW_GAP
  return { left, x: left ? COL.left : COL.right, y }
}

/**
 * The agent under review at the centre, the ten checks around it — one
 * spoke each. The point of the picture is that the specialists are not a
 * pipeline of ten steps but ten simultaneous questions asked of one
 * thing, which a list cannot say and a fan says immediately.
 */
export function SpecialistOrbit() {
  return (
    <div className="relative mx-auto w-full" style={{ maxWidth: BOX.w, aspectRatio: `${BOX.w} / ${BOX.h}` }}>
      {/* Spokes, behind everything. Dashed and faint on purpose: they carry
          the relationship, not the emphasis. Each starts at the hub's edge
          rather than its centre, so nothing appears to run under the card. */}
      <svg viewBox={`0 0 ${BOX.w} ${BOX.h}`} className="absolute inset-0 size-full" aria-hidden>
        {SPECIALISTS.map((id, i) => {
          const s = seat(i)
          const edge = HUB.x + (s.left ? -1 : 1) * (HUB.w / 2)
          // A gentle S-curve: leaves the hub horizontally, arrives at the
          // node horizontally. Straight lines to ten seats read as a
          // starburst; curves read as connections.
          const mid = (edge + s.x) / 2
          return (
            <path
              key={id}
              d={`M ${edge} ${HUB.y} C ${mid} ${HUB.y}, ${mid} ${s.y}, ${s.x} ${s.y}`}
              fill="none"
              stroke="color-mix(in oklab, var(--brand-blue) 38%, transparent)"
              strokeWidth={1}
              strokeDasharray="2.5 4"
            />
          )
        })}
      </svg>

      {/* The thing being checked. */}
      <div
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-xl border bg-card px-5 py-4 text-center shadow-sm"
        style={{ width: HUB.w }}
      >
        <BrandMark className="mx-auto size-10 rounded-lg" />
        <p className="mt-2.5 font-heading text-[14px] font-semibold leading-tight tracking-tight">
          The AI payment agent
        </p>
        <p className="mt-1.5 text-[11.5px] leading-snug text-muted-foreground">
          One agent, one submission, its complete record of runs
        </p>
      </div>

      {SPECIALISTS.map((id, i) => {
        const s = seat(i)
        const meta = nodeMeta(id)
        const Icon = meta.icon
        const tone = AGENT_ICON[meta.color]
        return (
          <div
            key={id}
            className={cn(
              'absolute flex -translate-y-1/2 items-center gap-2.5',
              // Anchored at the inner edge so both columns read outward from
              // the hub and each spoke lands on its roundel.
              s.left && '-translate-x-full flex-row-reverse',
            )}
            style={{ left: `${(s.x / BOX.w) * 100}%`, top: `${(s.y / BOX.h) * 100}%` }}
          >
            <span
              className={cn(
                'flex size-9 shrink-0 items-center justify-center rounded-lg ring-1 ring-inset',
                tone.bg,
                tone.ring,
              )}
            >
              <Icon className={cn('size-4.5', tone.text)} strokeWidth={2.25} />
            </span>
            <span className={cn('w-[132px] shrink-0', s.left && 'text-right')}>
              <span className="block font-heading text-[13px] font-semibold leading-tight tracking-tight">
                {meta.label}
              </span>
              <span className="mt-0.5 block text-[11.5px] leading-snug text-muted-foreground">{CHECKS[id]}</span>
            </span>
          </div>
        )
      })}
    </div>
  )
}
