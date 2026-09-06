import { useEffect, useState } from 'react'
import { useTheme } from 'next-themes'
import { Monitor, Moon, Sun } from 'lucide-react'
import { cn } from '@/lib/utils'

const OPTIONS = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'system', label: 'Match system', icon: Monitor },
  { value: 'dark', label: 'Dark', icon: Moon },
] as const

/**
 * A three-state segmented control, not a two-state switch: "match system" is
 * the default a console running all day should keep, and a plain toggle can't
 * express it. Renders a fixed-size placeholder until mounted so the header
 * doesn't shift when the resolved theme arrives.
 */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  if (!mounted) return <div className="h-7 w-[5.5rem]" aria-hidden />

  return (
    <div role="radiogroup" aria-label="Colour theme" className="flex items-center gap-0.5 rounded-md border bg-muted/50 p-0.5">
      {OPTIONS.map(({ value, label, icon: Icon }) => {
        const active = (theme ?? 'system') === value
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => setTheme(value)}
            className={cn(
              'flex size-6 items-center justify-center rounded-[5px] outline-none transition-colors',
              'focus-visible:ring-[3px] focus-visible:ring-ring/50',
              active
                ? 'bg-card text-foreground shadow-2xs'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <Icon className="size-3.5" />
          </button>
        )
      })}
    </div>
  )
}
