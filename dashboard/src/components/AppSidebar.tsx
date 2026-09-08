import { useEffect, useState } from 'react'
import { BookOpen, ClipboardList, FlaskConical, LayoutDashboard, ShieldAlert } from 'lucide-react'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from '@/components/ui/sidebar'
import { nodeMeta, SPECIALISTS } from '@/lib/node-meta'
import { cn } from '@/lib/utils'
import { BrandMark } from '@/components/BrandMark'

/** Working surfaces, plus one reference page per specialist. `agent:<id>`
 * keeps documentation in the same routing vocabulary without pretending an
 * agent is a feature you can operate. */
export type SectionName = 'overview' | 'queue' | 'sandbox' | 'catalogue' | 'rulebook' | `agent:${string}`

export function AppSidebar({
  section,
  onNavigate,
  queueCount,
}: {
  section: SectionName
  onNavigate: (section: SectionName) => void
  queueCount: number | null
}) {
  // A real, cheap health signal — pings the FastAPI backend once on mount
  // rather than showing a decorative always-green dot.
  const [healthy, setHealthy] = useState<boolean | null>(null)
  useEffect(() => {
    fetch(`${import.meta.env.VITE_SUPERVISOR_API_URL ?? 'http://127.0.0.1:8123'}/health`)
      .then((r) => setHealthy(r.ok))
      .catch(() => setHealthy(false))
  }, [])

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" onClick={() => onNavigate('overview')} className="group-data-[collapsible=icon]:justify-center">
              {/* Wrapped, not bare: SidebarMenuButton clamps any direct
                  <svg> child to size-4, which would shrink the mark to an
                  illegible 16px. The span takes that rule instead. */}
              <span className="flex size-9 shrink-0 items-center justify-center">
                <BrandMark className="size-9" />
              </span>
              <div className="grid leading-tight group-data-[collapsible=icon]:hidden">
                <span className="font-heading text-sm font-semibold tracking-tight">Mandate Supervisor</span>
                <span className="text-[11px] text-sidebar-foreground/60">Agentic payment oversight</span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Console</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton isActive={section === 'overview'} onClick={() => onNavigate('overview')} tooltip="Overview">
                  <LayoutDashboard />
                  <span>Overview</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton isActive={section === 'queue'} onClick={() => onNavigate('queue')} tooltip="Cases">
                  <ClipboardList />
                  <span>Cases</span>
                </SidebarMenuButton>
                {queueCount != null && queueCount > 0 && <SidebarMenuBadge>{queueCount}</SidebarMenuBadge>}
              </SidebarMenuItem>
              <SidebarMenuItem><SidebarMenuButton isActive={section === 'sandbox'} onClick={() => onNavigate('sandbox')} tooltip="Policy sandbox"><FlaskConical /><span>Policy sandbox</span></SidebarMenuButton></SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup className="group-data-[collapsible=icon]:hidden">
          {/* Documentation, not console. The group label is doing real work:
              these open reference pages explaining a specialist, they are not
              ten features you can run. */}
          <SidebarGroupLabel>Documentation</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {/* The two system-wide references first: the vocabulary of harm
                  and the rulebook. Every specialist page below is a slice of
                  these two, so they read better before the ten than after. */}
              <SidebarMenuItem>
                <SidebarMenuButton className="h-6.5 pl-5 text-[12.5px] font-normal text-sidebar-foreground/70 [&>svg]:size-3 [&>svg]:opacity-70" isActive={section === 'catalogue'} onClick={() => onNavigate('catalogue')} tooltip="Failure catalogue">
                  <ShieldAlert />
                  <span>Failure catalogue</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton className="h-6.5 pl-5 text-[12.5px] font-normal text-sidebar-foreground/70 [&>svg]:size-3 [&>svg]:opacity-70" isActive={section === 'rulebook'} onClick={() => onNavigate('rulebook')} tooltip="Rulebook">
                  <BookOpen />
                  <span>Rulebook</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              {/* Bare icons, no coloured tiles. Ten tinted swatches in a
                  narrow rail read as ten competing statuses, and they made
                  this group look unlike the Console group directly above it,
                  whose items are plain icons. The per-agent colour still does
                  its job where agents appear side by side — the pipeline
                  graph, the Overview fan — but in a nav list the selected row
                  is the only thing that should be carrying colour. */}
              {SPECIALISTS.map((id) => {
                const meta = nodeMeta(id)
                const Icon = meta.icon
                return (
                  <SidebarMenuItem key={id}>
                    <SidebarMenuButton
                      className="h-6.5 pl-5 text-[12.5px] font-normal text-sidebar-foreground/70 [&>svg]:size-3 [&>svg]:opacity-70"
                      isActive={section === `agent:${id}`}
                      onClick={() => onNavigate(`agent:${id}`)}
                      tooltip={meta.label}
                    >
                      <Icon />
                      <span>{meta.label}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

      </SidebarContent>

      {/* Just the health signal now — who is acting moved to the top bar,
          where an app shell puts identity and where it is read before a case
          is signed rather than after.

          A ruled strip across the foot of the rail, centred: it is a property
          of the whole console, not an item in the navigation, and the rule
          above it says so without a box drawn around the words. Offline is
          the only state that takes colour — everything else stays quiet. */}
      <SidebarFooter className="border-t border-sidebar-border/60 p-0">
        <div
          className="flex items-center justify-center gap-2 py-2.5"
          title={healthy == null ? 'Connecting to the pipeline' : healthy ? 'Pipeline online' : 'Pipeline offline'}
        >
          <span
            className={cn(
              'size-1.5 shrink-0 rounded-full ring-2',
              healthy == null
                ? 'bg-sidebar-foreground/30 ring-transparent'
                : healthy
                  ? 'bg-emerald-500 ring-emerald-500/20'
                  : 'bg-red-500 ring-red-500/25',
            )}
          />
          <span
            className={cn(
              'text-[11px] group-data-[collapsible=icon]:hidden',
              healthy === false ? 'font-medium text-red-600 dark:text-red-400' : 'text-sidebar-foreground/55',
            )}
          >
            {healthy == null ? 'Connecting…' : healthy ? 'Pipeline online' : 'Pipeline offline'}
          </span>
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
