import { useEffect } from 'react'
import { useSession } from '../state/sessionContext'
import type { Route } from '../state/route'
import { CandidatePanel } from '../components/CandidatePanel'
import { EvidenceGraph } from '../components/EvidenceGraph'
import { BeliefPanel } from '../components/BeliefPanel'
import { ActionPanel } from '../components/ActionPanel'
import { JustificationPanel } from '../components/JustificationPanel'
import { ResourcePanel } from '../components/ResourcePanel'
import { Timeline } from '../components/Timeline'

export function LoadState({ what }: { what: string }) {
  const s = useSession()
  if (s.phase === 'error')
    return (
      <div className="state" role="alert">
        <b>Cannot load {what}</b>
        <pre>{s.error}</pre>
        <span>
          Transport: {s.transport.label}.
          {s.transport.kind === 'live' && ' Start the MIRAGE API (default http://localhost:8000, proxied at /api), or use development data.'}
        </span>
        {s.transport.kind !== 'mock' && (
          <button className="btn" onClick={() => (window.location.search = '?transport=mock')}>
            OPEN WITH DEV / MOCK DATA
          </button>
        )}
      </div>
    )
  return (
    <div className="state" role="status">
      <b>Loading {what}…</b>
    </div>
  )
}

export function Cockpit({ navigate }: { navigate: (r: Route) => void }) {
  const s = useSession()

  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (t.closest('input, select, textarea, [role=dialog]')) return
      if (e.key === 'ArrowLeft') s.seek(s.cursor - 1)
      else if (e.key === 'ArrowRight') s.seek(s.cursor + 1)
      else if (e.key === ' ' && t.tagName !== 'BUTTON') {
        e.preventDefault()
        s.run()
      }
    }
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [s])

  if (!s.frame) return <LoadState what="episode" />

  return (
    <div className="cockpit">
      <div className="leftcol">
        <CandidatePanel />
        <JustificationPanel />
      </div>
      <EvidenceGraph />
      <BeliefPanel />
      <ActionPanel navigate={navigate} />
      <ResourcePanel />
      <Timeline />
    </div>
  )
}
