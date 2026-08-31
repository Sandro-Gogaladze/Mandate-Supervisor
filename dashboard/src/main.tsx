import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { CopilotKit } from '@copilotkit/react-core'
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
    <CopilotKit runtimeUrl={RUNTIME_URL} agent="mandate_supervisor" showDevConsole={false} enableInspector={false}>
      <TooltipProvider>
        <App />
        <Toaster position="bottom-right" />
      </TooltipProvider>
    </CopilotKit>
  </StrictMode>,
)
