import { useEffect, useState } from 'react'
import { useSession } from '../state/sessionContext'
import type { Route } from '../state/route'
import { CandidatePanel } from '../components/CandidatePanel'
import { EvidenceGraph } from '../components/EvidenceGraph'
import { BeliefPanel } from '../components/BeliefPanel'
import { ActionPanel } from '../components/ActionPanel'
import { JustificationPanel } from '../components/JustificationPanel'
import { ResourcePanel } from '../components/ResourcePanel'
import { Timeline } from '../components/Timeline'
import { GuidedCoach } from '../components/GuidedCoach'
import { PathStrip } from '../components/PathStrip'
import { CampaignStory } from '../components/CampaignStory'
import type { DrawerId } from '../lib/drawers'
import type { Focus } from '../lib/guided'

export function LoadState({ what }: { what: string }) {
  const s = useSession()
  if (s.phase === 'error')
    return (
      <div className="state" role="alert">
        <b>Cannot load {what}</b>
        <pre>{s.error}</pre>
        <span>
          Transport: {s.transport.label}.{s.transport.kind === 'live' && ' Start everything with ./mirage demo (it starts the API and wires the proxy), or open the System check tab.'}
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

type View = 'story' | 'full'
const VIEW_KEY = 'mirage.cockpit.view'

function readView(): View {
  try {
    return window.localStorage.getItem(VIEW_KEY) === 'full' ? 'full' : 'story'
  } catch {
    return 'story'
  }
}

/** Every panel at once: the instrument view for people who already know the cockpit. */
function FullCockpit({ navigate }: { navigate: (r: Route) => void }) {
  const s = useSession()
  const [focus, setFocus] = useState<Focus | null>(null)
  return (
    <>
      <PathStrip focus={focus} />
      {s.launch.guided && s.transport.kind === 'live' && <GuidedCoach key={s.session?.session_id} onFocus={setFocus} />}
      <div className="cockpit" data-focus={focus ?? undefined}>
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
    </>
  )
}

export function Cockpit({ navigate }: { navigate: (r: Route) => void }) {
  const s = useSession()
  const [view, setView] = useState<View>(readView)
  const [drawer, setDrawer] = useState<DrawerId | null>(null)

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

  const choose = (v: View) => {
    setView(v)
    setDrawer(null)
    try {
      window.localStorage.setItem(VIEW_KEY, v)
    } catch {
      /* private mode: the choice just isn't remembered */
    }
  }

  if (!s.frame) return <LoadState what="episode" />

  return (
    <div className={`cockwrap cockwrap--${view}`}>
      <div className="viewtoggle" role="group" aria-label="Cockpit layout">
        <button className="viewtoggle__btn" aria-pressed={view === 'story'} onClick={() => choose('story')} title="One step at a time, with the rest in side panels">
          Step by step
        </button>
        <button className="viewtoggle__btn" aria-pressed={view === 'full'} onClick={() => choose('full')} title="Every panel on one screen">
          All panels
        </button>
      </div>
      {view === 'story' ? <CampaignStory navigate={navigate} drawer={drawer} setDrawer={setDrawer} /> : <FullCockpit navigate={navigate} />}
    </div>
  )
}
