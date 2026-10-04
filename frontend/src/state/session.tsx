import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { EpisodeSession, ScientificTransport } from '../lib/transport'
import { SessionContext } from './sessionContext'
import type { SessionApi } from './sessionContext'
import type { ManualChoice, Phase } from './sessionContext'
import { appendManualChoice } from './manual'
import { launchFromSearch } from './launch'
import { projectEpisode } from '../lib/project'
import type { Catalogue, EpisodeSummary, LaunchConfig, PolicyComparison } from '../lib/types'
import type { ActionType } from '../lib/wire'

/** Short pause so RUN reads as an experiment being executed, not a page flip. */
const RUN_LATENCY_MS = 520
const PLAY_INTERVAL_MS = 1700

export function SessionProvider({ transport, children }: { transport: ScientificTransport; children: ReactNode }) {
  const [episodes, setEpisodes] = useState<EpisodeSummary[]>([])
  const [launch, setLaunch] = useState<LaunchConfig>(() => launchFromSearch(typeof location === 'undefined' ? '' : location.search))
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null)
  const [catalogueState, setCatalogueState] = useState<'loading' | 'ready' | 'unavailable'>('loading')
  const [manualLog, setManualLog] = useState<ManualChoice[]>([])
  const [scenarioId, setScenarioId] = useState<string | null>(null)
  const [policyName, setPolicyName] = useState<string | null>(null)
  const [session, setSession] = useState<EpisodeSession | null>(null)
  const [cursor, setCursor] = useState(0)
  const [selection, setSelection] = useState<string | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const [error, setError] = useState<string | null>(null)
  const [playing, setPlaying] = useState(false)
  const [cmpState, setCmpState] = useState<{ id: string; value: PolicyComparison | null; error?: string } | null>(null)
  const openToken = useRef(0)
  const [restart, setRestart] = useState(0)

  const frames = useMemo(() => (session ? projectEpisode(session.record) : []), [session])

  const fail = useCallback((e: unknown) => {
    setError(e instanceof Error ? e.message : String(e))
    setPhase('error')
    setPlaying(false)
  }, [])

  useEffect(() => {
    let alive = true
    if (!transport.catalogue) return
    transport
      .catalogue()
      .then((c) => {
        if (!alive) return
        setCatalogue(c)
        setCatalogueState('ready')
      })
      .catch(() => alive && setCatalogueState('unavailable'))
    return () => {
      alive = false
    }
  }, [transport])

  useEffect(() => {
    let alive = true
    transport
      .listEpisodes()
      .then((eps) => {
        if (!alive) return
        if (eps.length === 0) throw new Error('Backend returned no episodes')
        setEpisodes(eps)
        // A seed from the URL / launcher wins over the catalogue's first entry.
        const pick = eps.find((e) => e.seed === launch.seed && (!launch.policy || e.policy.name === launch.policy)) ?? eps.find((e) => e.seed === launch.seed) ?? eps[0]
        setScenarioId(pick.scenario.id)
        setPolicyName(pick.policy.name)
      })
      .catch((e) => alive && fail(e))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the URL choice is read once, at load
  }, [transport, fail])

  const options = useMemo(() => ({ scenario: launch.scenario, semantics: launch.semantics }), [launch.scenario, launch.semantics])

  useEffect(() => {
    if (!scenarioId) return
    const token = ++openToken.current
    transport
      .openEpisode(scenarioId, policyName ?? undefined, options)
      .then((s) => {
        if (token !== openToken.current) return
        setSession(s)
        setCursor(0)
        setSelection(null)
        setPlaying(false)
        setError(null)
        setManualLog([])
        setPhase('ready')
      })
      .catch((e) => token === openToken.current && fail(e))
  }, [transport, scenarioId, policyName, restart, options, fail])

  useEffect(() => {
    if (!scenarioId) return
    let alive = true
    transport
      .getPolicyComparison(scenarioId, options)
      .then((c) => alive && setCmpState({ id: scenarioId, value: c }))
      .catch((e) => alive && setCmpState({ id: scenarioId, value: null, error: e instanceof Error ? e.message : String(e) }))
    return () => {
      alive = false
    }
  }, [transport, scenarioId, options])

  const cmpHere = cmpState && cmpState.id === scenarioId ? cmpState : null
  const comparison = cmpHere ? cmpHere.value : undefined
  const comparisonError = cmpHere?.error ?? null
  const atEnd = frames.length > 0 && cursor >= frames.length - 1
  const terminal = frames[cursor]?.status === 'terminal'
  const canRun = phase === 'ready' && !terminal && (!atEnd || (session?.mode === 'live' && !session.record.complete))

  const run = useCallback(() => {
    if (!session || phase !== 'ready') return
    if (cursor < frames.length - 1) {
      setPhase('running')
      window.setTimeout(() => {
        setCursor((c) => Math.min(c + 1, frames.length - 1))
        setPhase('ready')
      }, RUN_LATENCY_MS)
      return
    }
    if (session.mode === 'live' && !session.record.complete) {
      setPhase('running')
      transport
        .step(session.session_id)
        .then((s) => {
          setSession(s)
          setCursor(frames.length)
          setPhase('ready')
        })
        .catch(fail)
    }
  }, [session, phase, cursor, frames.length, transport, fail])

  const act = useCallback(
    (action: ActionType) => {
      if (!session || phase !== 'ready' || !transport.act || cursor < frames.length - 1) return
      const recommended = frames[frames.length - 1]?.recommendation?.action_type ?? null
      setPhase('running')
      transport
        .act(session.session_id, action)
        .then((s) => {
          setSession(s)
          setCursor(frames.length)
          setManualLog((l) => appendManualChoice(l, frames.length, action, recommended))
          setPhase('ready')
        })
        .catch(fail)
    },
    [session, phase, transport, cursor, frames, fail],
  )

  const scenarioEntry = useMemo(() => {
    const list = catalogue?.scenarios ?? []
    return list.find((x) => x.id === launch.scenario || x.cli_name === launch.scenario) ?? (launch.scenario === null ? (list.find((x) => x.is_default) ?? null) : null)
  }, [catalogue, launch.scenario])

  // Autoplay stops by itself when nothing can run; no state write needed.
  const isPlaying = playing && canRun
  useEffect(() => {
    if (!isPlaying) return
    const id = window.setInterval(() => run(), PLAY_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [isPlaying, run])

  const api = useMemo<SessionApi>(
    () => ({
      transport,
      episodes,
      scenarioId,
      policyName,
      session,
      frames,
      cursor,
      frame: frames[cursor] ?? null,
      prevFrame: cursor > 0 ? frames[cursor - 1] : null,
      selection,
      phase,
      error,
      playing: isPlaying,
      atEnd,
      canRun,
      comparison,
      comparisonError,
      launch,
      catalogue,
      catalogueState: transport.catalogue ? catalogueState : 'unavailable',
      scenarioEntry,
      manualLog,
      launchCampaign: (cfg) => {
        const next = { ...launch, ...cfg }
        setLaunch(next)
        setScenarioId(`seed-${next.seed}`)
        if (next.policy) setPolicyName(next.policy)
        else setPolicyName((p) => p ?? episodes[0]?.policy.name ?? null)
        setRestart((n) => n + 1)
      },
      act,
      endGuided: () => setLaunch((l) => ({ ...l, guided: false })),
      startCampaign: (seed) => {
        setLaunch((l) => ({ ...l, seed }))
        setScenarioId(`seed-${seed}`)
        setPolicyName((p) => p ?? episodes[0]?.policy.name ?? null)
        setRestart((n) => n + 1)
      },
      selectScenario: (id) => {
        setPolicyName((p) => episodes.find((e) => e.scenario.id === id)?.policy.name ?? p)
        setScenarioId(id)
      },
      selectPolicy: (name) => {
        setPolicyName(name)
        setLaunch((l) => ({ ...l, policy: name }))
      },
      run,
      seek: (i) => {
        setPlaying(false)
        setCursor(Math.max(0, Math.min(i, frames.length - 1)))
      },
      reset: () => {
        setPlaying(false)
        setCursor(0)
        setSelection(null)
      },
      togglePlay: () => {
        if (cursor >= frames.length - 1 && session?.mode === 'replay') setCursor(0)
        setPlaying((p) => !p)
      },
      select: setSelection,
    }),
    [transport, episodes, scenarioId, policyName, session, frames, cursor, selection, phase, error, isPlaying, atEnd, canRun, comparison, comparisonError, run, launch, catalogue, catalogueState, scenarioEntry, manualLog, act],
  )

  return <SessionContext.Provider value={api}>{children}</SessionContext.Provider>
}
