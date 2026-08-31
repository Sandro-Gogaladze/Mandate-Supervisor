// Thin CopilotKit Runtime — the one piece of this stack that isn't Python.
//
// @copilotkit/react-core's hooks (useCoAgent, useCoAgentStateRender,
// useCopilotAction) speak CopilotKit's GraphQL runtime protocol via
// `runtimeUrl`; they cannot point at a raw AG-UI endpoint directly. This
// server does nothing but that translation: it registers our FastAPI
// backend's already-AG-UI-compliant `/agent` endpoint (api/main.py, built
// on ag_ui_langgraph) as a single `HttpAgent` and re-exposes it to the
// browser. No LLM adapter, no chat model, no business logic lives here —
// every real decision (dispatch, specialists, scoring) happens in the
// Python graph this just forwards to.
import cors from 'cors'
import express from 'express'
import { HttpAgent } from '@ag-ui/client'
import { CopilotRuntime } from '@copilotkit/runtime/v2'
import { createCopilotExpressHandler } from '@copilotkit/runtime/v2/express'

const BACKEND_URL = process.env.SUPERVISOR_API_URL ?? 'http://127.0.0.1:8123'
const PORT = Number(process.env.COPILOT_RUNTIME_PORT ?? 4000)

// A long-running case review (escalation loop + several specialists, each
// making its own streamed LLM call) can push the FastAPI SSE response past
// what the OS/uvicorn keeps open without a hitch. When that connection is
// cut mid-stream, @ag-ui/client's HttpAgent (via undici's fetch) throws a
// bare `TypeError: terminated` as an *unhandled promise rejection* — not
// caught anywhere in that call chain — which is fatal by default in modern
// Node and takes the whole process down, breaking every other in-flight or
// future run until this process is restarted. Confirmed live: one heavy
// case run left this log with `SocketError: other side closed` after
// reading ~2.7MB, and every case run after that got ERR_CONNECTION_REFUSED
// until the process was manually restarted. A dropped run should surface
// as a failed run in the UI, not silently take the whole demo offline —
// this is the last line of defense against that, distinct from (and in
// addition to) fixing the underlying cause of any given disconnect.
process.on('unhandledRejection', (err) => {
  console.error('[copilot-runtime] Unhandled rejection (likely a dropped upstream connection to the backend); ignoring to keep the server alive:', err)
})
process.on('uncaughtException', (err) => {
  console.error('[copilot-runtime] Uncaught exception; ignoring to keep the server alive:', err)
})

// Three agents, one per run kind (architecture-v2 §14): triage is the
// multi-agent showpiece, session is the conversational orchestrator,
// drafter carries the human gate (interrupt outcome + resume).
const runtime = new CopilotRuntime({
  agents: {
    mandate_supervisor: new HttpAgent({ url: `${BACKEND_URL}/agent/triage` }),
    supervisor_session: new HttpAgent({ url: `${BACKEND_URL}/agent/session` }),
    report_drafter: new HttpAgent({ url: `${BACKEND_URL}/agent/drafter` }),
  },
})

const app = express()
app.use(cors())
// Mounted at root, not app.use('/copilotkit', ...): createCopilotExpressHandler's
// router matches routes against its own `basePath` internally
// (`^/copilotkit(/.*)?$`) — mounting it under an Express path prefix as well
// would double that prefix and 404 every request.
app.use(createCopilotExpressHandler({ runtime, basePath: '/copilotkit' }))

app.listen(PORT, () => {
  console.log(`CopilotKit runtime listening on http://localhost:${PORT}/copilotkit`)
  console.log(`  -> triage:  mandate_supervisor -> ${BACKEND_URL}/agent/triage`)
  console.log(`  -> session: supervisor_session -> ${BACKEND_URL}/agent/session`)
  console.log(`  -> drafter: report_drafter     -> ${BACKEND_URL}/agent/drafter`)
})
