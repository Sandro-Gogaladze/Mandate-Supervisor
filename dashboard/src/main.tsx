import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { CopilotKit } from '@copilotkit/react-core/v2'
import { ThemeProvider } from 'next-themes'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Toaster } from '@/components/ui/sonner'
import App from './App.tsx'
import '@xyflow/react/dist/style.css'
import './index.css'

const RUNTIME_URL = import.meta.env.VITE_COPILOT_RUNTIME_URL ?? 'http://localhost:4000/copilotkit'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* showDevConsole only governs toasts in the v1-compat wrapper — the
        floating cpk-web-inspector bubble is gated by enableInspector, which
        defaults to "on when localhost". Off explicitly: no foreign dev
        chrome on the supervision console (confirmed in the bundled
        CopilotKit source: shouldShowDevConsole(props.enableInspector)). */}
    {/* Light is the console's default look and does not follow the OS — a
        supervisor opening this on a dark-mode laptop should still get the
        paper surface the design is drawn for. Dark is fully specified in
        index.css and reachable from the header toggle, which also feeds
        sonner's useTheme() for the toast surface. */}
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem disableTransitionOnChange>
      <CopilotKit runtimeUrl={RUNTIME_URL} agent="mandate_supervisor" showDevConsole={false} enableInspector={false}>
        <TooltipProvider>
          <App />
          <Toaster position="bottom-right" />
        </TooltipProvider>
      </CopilotKit>
    </ThemeProvider>
  </StrictMode>,
)
