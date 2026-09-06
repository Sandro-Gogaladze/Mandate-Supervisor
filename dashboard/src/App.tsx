import { useEffect, useMemo, useState } from 'react'
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import { Separator } from '@/components/ui/separator'
import { AppSidebar, type SectionName } from '@/components/AppSidebar'
import { Overview } from '@/components/Overview'
import { CaseQueue } from '@/components/CaseQueue'
import { CaseReview } from '@/components/CaseReview'
import { PolicySandbox } from '@/components/PolicySandbox'
import { AgentPage } from '@/components/AgentPage'
import { CataloguePage } from '@/components/CataloguePage'
import { RulebookPage } from '@/components/RulebookPage'
import { nodeMeta } from '@/lib/node-meta'
import { ThemeToggle } from '@/components/ThemeToggle'
import { listCases } from '@/lib/api'
import type { CaseSummary } from '@/lib/types'

function App() {
  const [section, setSection] = useState<SectionName>('overview')
  const [openCase, setOpenCase] = useState<CaseSummary | null>(null)
  const [queueCount, setQueueCount] = useState<number | null>(null)

  useEffect(() => {
    listCases()
      .then((cases) => setQueueCount(cases.length))
      .catch(() => setQueueCount(null))
  }, [])

  const navigate = (next: SectionName) => {
    setSection(next)
    setOpenCase(null)
  }

  const handleOpenCase = (c: CaseSummary) => {
    setSection('queue')
    setOpenCase(c)
  }

  const today = useMemo(
    () => new Date().toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }),
    [],
  )

  const agentId = section.startsWith('agent:') ? section.slice('agent:'.length) : null

  const crumb = openCase
    ? `Cases · ${openCase.case_id}`
    : agentId
      ? `Documentation · ${nodeMeta(agentId).label}`
      : section === 'catalogue'
      ? 'Documentation · Failure catalogue'
      : section === 'rulebook'
      ? 'Documentation · Rulebook'
      : section === 'overview'
        ? 'Overview'
        : section === 'sandbox' ? 'Policy sandbox' : 'Cases'

  return (
    <SidebarProvider>
      <AppSidebar section={section} onNavigate={navigate} queueCount={queueCount} />
      <SidebarInset className="h-svh overflow-hidden">
        <header className="flex h-12 shrink-0 items-center gap-2 border-b bg-card px-4">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-1 !h-4" />
          <span className="text-sm font-medium">{crumb}</span>
          <div className="ml-auto flex items-center gap-3">
            <span className="font-mono text-[11px] text-muted-foreground">{today}</span>
            <ThemeToggle />
          </div>
        </header>
        <div className="min-h-0 flex-1">
          {openCase ? (
            // Keyed by case: the CopilotKit agents are registry SINGLETONS shared
            // by every case, and without a remount switching dossiers only ran an
            // effect over that shared state. Subscriptions, in-flight runs and the
            // agent's own case_id could then belong to the case you just left —
            // which is how a review fired against one dossier while the console
            // was showing another.
            <CaseReview key={openCase.case_id} caseSummary={openCase} onBack={() => setOpenCase(null)} />
          ) : section === 'catalogue' ? (
            <div className="h-full overflow-auto"><CataloguePage /></div>
          ) : section === 'rulebook' ? (
            <div className="h-full overflow-auto">
              <RulebookPage onOpenAgent={(id) => navigate(`agent:${id}`)} onOpenSandbox={() => navigate('sandbox')} />
            </div>
          ) : agentId ? (
            <div className="h-full overflow-auto">
              <AgentPage key={agentId} agentId={agentId} />
            </div>
          ) : section === 'overview' ? (
            <div className="h-full overflow-auto">
              <Overview onOpenQueue={() => navigate('queue')} onOpenCase={handleOpenCase} />
            </div>
          ) : section === 'sandbox' ? (
            <PolicySandbox />
          ) : (
            <div className="h-full overflow-auto">
              <CaseQueue onSelect={handleOpenCase} />
            </div>
          )}
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}

export default App
