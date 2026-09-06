import { useEffect, useState } from 'react'
import { BookOpen, ClipboardList, FlaskConical, LayoutDashboard, ShieldAlert, UserRound } from 'lucide-react'
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
import { DEFAULT_OFFICER, useOfficer } from '@/lib/officer'
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
  const [officer, setOfficer] = useOfficer()
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

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <div className="flex items-center gap-2 rounded-md px-2 py-1.5 group-data-[collapsible=icon]:justify-center">
              <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-sidebar-accent">
                <UserRound className="size-3.5 text-sidebar-foreground/70" />
              </div>
              <div className="grid leading-tight group-data-[collapsible=icon]:hidden">
                <input
                  value={officer}
                  onChange={(e) => setOfficer(e.target.value)}
                  onBlur={(e) => !e.target.value.trim() && setOfficer(DEFAULT_OFFICER)}
                  placeholder={DEFAULT_OFFICER}
                  aria-label="Acting as — recorded on everything you do"
                  className="w-full bg-transparent text-xs font-medium outline-none placeholder:text-sidebar-foreground/50 focus:underline"
                />
                <span className="flex items-center gap-1.5 text-[10px] text-sidebar-foreground/60">
                  <span
                    className={cn(
                      'size-1.5 rounded-full',
                      healthy == null ? 'bg-sidebar-foreground/30' : healthy ? 'bg-emerald-400' : 'bg-red-400',
                    )}
                  />
                  {healthy == null ? 'connecting…' : healthy ? 'pipeline online' : 'pipeline offline'}
                </span>
              </div>
            </div>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
