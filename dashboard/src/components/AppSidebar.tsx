import { useEffect, useState } from 'react'
import { ClipboardList, LayoutDashboard, UserRound } from 'lucide-react'
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
import { nodeMeta, SPECIALISTS, AGENT_ICON } from '@/lib/node-meta'
import { cn } from '@/lib/utils'

export type SectionName = 'overview' | 'queue'

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
              {/* logo-dark-bg.png is the light-on-dark variant of the mark
                  (navy figure → paper white, robot blue kept) so it sits
                  directly on the ink rail, no plate needed. */}
              <img src="/logo-dark-bg.png" alt="Mandate Supervisor logo" className="size-8 shrink-0 object-contain" />
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
                <SidebarMenuButton isActive={section === 'queue'} onClick={() => onNavigate('queue')} tooltip="Case queue">
                  <ClipboardList />
                  <span>Case queue</span>
                </SidebarMenuButton>
                {queueCount != null && queueCount > 0 && <SidebarMenuBadge>{queueCount}</SidebarMenuBadge>}
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup className="group-data-[collapsible=icon]:hidden">
          <SidebarGroupLabel>Review specialists</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {SPECIALISTS.map((id) => {
                const meta = nodeMeta(id)
                const Icon = meta.icon
                const tone = AGENT_ICON[meta.color]
                return (
                  <SidebarMenuItem key={id}>
                    {/* Informational roster, not navigation — the agents are
                        not pages, they're the workforce. */}
                    <div className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-sidebar-foreground/80">
                      <span className={cn('flex size-5 items-center justify-center rounded', tone.bg)}>
                        <Icon className={cn('size-3.5', tone.text)} />
                      </span>
                      <span>{meta.label}</span>
                      <span className="ml-auto size-1.5 rounded-full bg-emerald-400/80" title="ready" />
                    </div>
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
                <span className="text-xs font-medium">Case officer</span>
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
