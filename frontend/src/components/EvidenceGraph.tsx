import { useEffect, useMemo } from 'react'
import { Background, BackgroundVariant, Handle, Position, ReactFlow, ReactFlowProvider, useReactFlow } from '@xyflow/react'
import type { Edge, Node, NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useSession } from '../state/sessionContext'
import { Panel } from './ui'
import { buildGraph, mechanismStatus, neighbourhood, SPR_DAMAGE } from '../lib/derive'
import type { EdgeRelation, GraphNode } from '../lib/derive'
import type { CockpitState, EventView } from '../lib/types'
import { actionShort, formatMeasurement, isPoorQuality, measurementLabel } from '../lib/actions'
import { fmtMoney, fmtP, fmtT, MECH_LABEL } from '../lib/format'

const COL_X = [0, 262, 612]
const NODE_W = [196, 196, 168]
const ROW_H = 76
const MECH_GAP = 64

interface NodeData extends Record<string, unknown> {
  g: GraphNode
  p?: number
  status?: ReturnType<typeof mechanismStatus>
  isNew: boolean
  selected: boolean
  dim: boolean
}
type FlowNode = Node<NodeData>

const KIND_LABEL: Record<string, string> = {
  failure: 'OBSERVED FAILURE',
  action: 'EXPERIMENT',
  observation: 'OBSERVATION',
  redesign: 'REDESIGN',
  decision: 'TERMINAL DECISION',
}

function EventNode({ data }: NodeProps<FlowNode>) {
  const ev = data.g.event as EventView
  const kind = data.g.kind
  const obs = ev.observation
  const cls = ['gn', `gn--${kind}`, data.isNew && 'is-new', data.selected && 'is-selected', data.dim && 'is-dim'].filter(Boolean).join(' ')
  return (
    <div className={cls} style={{ width: NODE_W[data.g.col] }}>
      <Handle id="l" type="target" position={Position.Left} className="gn__h" isConnectable={false} />
      <Handle id="t" type="target" position={Position.Top} className="gn__h" isConnectable={false} />
      <div className="gn__top">
        <span className="gn__kind">{KIND_LABEL[kind]}</span>
        {kind === 'action' && ev.action_type && <span className="chip">{actionShort(ev.action_type)}</span>}
        {kind === 'observation' && obs && <span className={`chip ${isPoorQuality(obs.quality) ? 'chip--contra' : 'chip--support'}`}>{obs.quality.toUpperCase()}</span>}
        {kind === 'redesign' && ev.result_candidate_id && <span className="chip chip--accent">{ev.result_candidate_id.split('-').pop()}</span>}
        {kind === 'action' && ev.spr_delta < -SPR_DAMAGE && <span className="chip chip--contra">SPR {ev.spr_delta.toFixed(2)}</span>}
      </div>
      {kind === 'observation' && obs ? (
        <div className="gn__meas mono">
          {obs.measurements.map((m) => (
            <div key={m.name}>
              <span className="faint">{measurementLabel(m.name)}</span> {formatMeasurement(m.name, m.value)}
            </div>
          ))}
        </div>
      ) : (
        <>
          <div className="gn__title">{kind === 'failure' ? ev.notes[0] : ev.title}</div>
          <div className="gn__sub mono">
            {kind === 'failure' && fmtT(ev.t_h)}
            {kind === 'action' && (
              <>
                {ev.candidate_id} · {fmtMoney(ev.cost.budget)} · {ev.cost.time} h
              </>
            )}
            {kind === 'redesign' && (
              <>
                {fmtMoney(ev.cost.budget)} · {ev.cost.time} h
              </>
            )}
            {kind === 'decision' && ev.candidate_id}
          </div>
        </>
      )}
      <Handle id="r" type="source" position={Position.Right} className="gn__h" isConnectable={false} />
      <Handle id="b" type="source" position={Position.Bottom} className="gn__h" isConnectable={false} />
    </div>
  )
}

function MechNode({ data }: NodeProps<FlowNode>) {
  const status = data.status!
  const cls = ['gm', `gm--${status}`, data.selected && 'is-selected', data.dim && 'is-dim'].filter(Boolean).join(' ')
  return (
    <div className={cls} style={{ width: NODE_W[2] }}>
      <Handle id="l" type="target" position={Position.Left} className="gn__h" isConnectable={false} />
      <div className="gm__name">{MECH_LABEL[data.g.mechanism!]}</div>
      <div className="gm__p mono">{fmtP(data.p!)}</div>
      <div className="gm__tag">{status === 'active' ? 'LEADING' : status === 'ruled_out' ? 'UNLIKELY' : 'OPEN'}</div>
      <span className="gm__bar" style={{ width: `${(data.p ?? 0) * 100}%` }} />
    </div>
  )
}

const nodeTypes = { event: EventNode, mech: MechNode }

const EDGE_STYLE: Record<EdgeRelation, { stroke: string; dash?: string; marker: string }> = {
  supports: { stroke: 'var(--support)', marker: 'mk-support' },
  contradicts: { stroke: 'var(--contra)', dash: '7 4', marker: 'mk-contra' },
  unresolved: { stroke: 'var(--unres)', dash: '1.5 4', marker: 'mk-unres' },
  targets: { stroke: 'var(--accent)', dash: '10 3 2 3', marker: 'mk-targets' },
  flow: { stroke: 'var(--line-3)', marker: 'mk-flow' },
}

function layout(frame: CockpitState, selection: string | null) {
  const graph = buildGraph(frame)
  const near = neighbourhood(graph, selection)
  const totalH = Math.max(graph.rows * ROW_H, 8 * MECH_GAP)
  const mechTop = (totalH - 8 * MECH_GAP) / 2

  const nodes: FlowNode[] = graph.nodes.map((g) => {
    const isMech = g.kind === 'mechanism'
    const p = isMech ? frame.belief.p[g.mechanism!] : undefined
    return {
      id: g.id,
      type: isMech ? 'mech' : 'event',
      position: { x: COL_X[g.col], y: isMech ? mechTop + g.row * MECH_GAP : g.row * ROW_H },
      draggable: false,
      connectable: false,
      data: { g, p, status: p === undefined ? undefined : mechanismStatus(p), isNew: g.step === frame.step, selected: selection === g.id, dim: selection !== null && !near.has(g.id) },
    }
  })

  const edges: Edge[] = graph.edges.map((e) => {
    const st = EDGE_STYLE[e.relation]
    const connected = selection !== null && (e.source === selection || e.target === selection)
    const dim = selection !== null && !connected
    const evidence = e.relation === 'supports' || e.relation === 'contradicts' || e.relation === 'unresolved'
    const spine = e.relation === 'flow' && graph.nodes.find((n) => n.id === e.source)?.col === graph.nodes.find((n) => n.id === e.target)?.col
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: spine ? 'b' : 'r',
      targetHandle: spine ? 't' : 'l',
      type: evidence ? 'default' : spine || e.relation === 'flow' ? 'straight' : 'smoothstep',
      markerEnd: st.marker,
      selectable: false,
      focusable: false,
      style: {
        stroke: st.stroke,
        strokeDasharray: st.dash,
        strokeWidth: evidence ? 1.1 + e.weight * 1.6 + (connected ? 0.8 : 0) : 1,
        opacity: dim ? 0.1 : evidence ? 0.45 + e.weight * 0.5 : e.relation === 'targets' ? 0.7 : 0.55,
      },
    }
  })
  return { nodes, edges, rows: graph.rows }
}

function Fit({ trigger }: { trigger: string }) {
  const { fitView } = useReactFlow()
  useEffect(() => {
    const id = requestAnimationFrame(() => fitView({ padding: 0.1, maxZoom: 1.15, minZoom: 0.3, duration: 380 }))
    return () => cancelAnimationFrame(id)
  }, [trigger, fitView])
  return null
}

function Markers() {
  const mk = (id: string, color: string, shape: 'arrow' | 'bar' | 'ring') => (
    <marker key={id} id={id} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse" markerUnits="userSpaceOnUse">
      {shape === 'arrow' && <path d="M0,1 L9,5 L0,9 z" style={{ fill: color }} />}
      {shape === 'bar' && <path d="M8,0 L8,10" style={{ stroke: color, strokeWidth: 2.2 }} />}
      {shape === 'ring' && <circle cx="6" cy="5" r="2.8" style={{ fill: 'none', stroke: color, strokeWidth: 1.4 }} />}
    </marker>
  )
  return (
    <svg className="rf-markers" aria-hidden>
      <defs>
        {mk('mk-support', 'var(--support)', 'arrow')}
        {mk('mk-contra', 'var(--contra)', 'bar')}
        {mk('mk-unres', 'var(--unres)', 'ring')}
        {mk('mk-targets', 'var(--accent)', 'arrow')}
        {mk('mk-flow', 'var(--line-3)', 'arrow')}
      </defs>
    </svg>
  )
}

function Legend() {
  const sw = (relation: EdgeRelation, label: string) => (
    <span className="glegend__i">
      <svg width="28" height="8" aria-hidden>
        <line x1="1" x2="27" y1="4" y2="4" style={{ stroke: EDGE_STYLE[relation].stroke, strokeDasharray: EDGE_STYLE[relation].dash, strokeWidth: 1.8 }} />
      </svg>
      {label}
    </span>
  )
  return (
    <span className="glegend">
      {sw('supports', 'raises belief')}
      {sw('contradicts', 'lowers belief')}
      {sw('unresolved', 'unresolved')}
      {sw('targets', 'redesign aim')}
      <span className="glegend__i">
        <i className="glegend__ring" /> leading
      </span>
    </span>
  )
}

const REL_CHIP = { supports: ['support', '+ raises'], contradicts: ['contra', '− lowers'], unresolved: ['unres', '? unresolved'] } as const

function SelectionCard({ frame, selection, onClose }: { frame: CockpitState; selection: string; onClose: () => void }) {
  if (selection.startsWith('m:')) {
    const m = selection.slice(2) as keyof typeof MECH_LABEL
    const hits = frame.events.flatMap((e) => e.links.filter((l) => l.mechanism === m).map((l) => ({ e, l })))
    return (
      <aside className="gsel" aria-live="polite">
        <header>
          <b>{MECH_LABEL[m]}</b>
          <span className="mono">p = {fmtP(frame.belief.p[m as keyof typeof frame.belief.p])}</span>
          <button onClick={onClose} aria-label="Clear selection">×</button>
        </header>
        {hits.length === 0 ? (
          <p className="dim">No measurement has yet borne on this failure mode. Prior only, or moved by a redesign.</p>
        ) : (
          <ul>
            {hits.map(({ e, l }) => (
              <li key={e.id}>
                <span className={`chip chip--${REL_CHIP[l.relation][0]}`}>{REL_CHIP[l.relation][1]}</span>
                <span>{e.title}</span>
                <span className="mono faint">step {e.step}</span>
              </li>
            ))}
          </ul>
        )}
      </aside>
    )
  }
  const ev = frame.events.find((e) => e.id === selection.replace(/:obs$/, ''))
  if (!ev) return null
  return (
    <aside className="gsel" aria-live="polite">
      <header>
        <b>{ev.title}</b>
        <span className="mono faint">
          step {ev.step} · {fmtT(ev.t_h)}
        </span>
        <button onClick={onClose} aria-label="Clear selection">×</button>
      </header>
      {ev.notes.map((n) => (
        <p key={n}>{n}</p>
      ))}
      {ev.observation && (
        <>
          <p className="mono">
            {ev.observation.measurements.map((m) => `${measurementLabel(m.name)} ${formatMeasurement(m.name, m.value)}`).join(' · ')} · quality {ev.observation.quality}
          </p>
          {ev.observation.notes.map((n) => (
            <p key={n} className="dim">{n}</p>
          ))}
        </>
      )}
      {ev.rationale && <p className="dim">Policy rationale: {ev.rationale}</p>}
      {ev.links.length > 0 && (
        <ul>
          {ev.links.map((l) => (
            <li key={l.mechanism}>
              <span className={`chip chip--${REL_CHIP[l.relation][0]}`}>{REL_CHIP[l.relation][1]}</span>
              <span>{MECH_LABEL[l.mechanism]}</span>
              {ev.belief_before && (
                <span className="mono faint">
                  {fmtP(ev.belief_before.p[l.mechanism])} → {fmtP(ev.belief_after.p[l.mechanism])}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}

function Inner() {
  const { frame, selection, select } = useSession()
  const built = useMemo(() => (frame ? layout(frame, selection) : null), [frame, selection])
  if (!frame || !built) return null
  return (
    <div className="graph">
      <Markers />
      <ReactFlow
        nodes={built.nodes}
        edges={built.edges}
        nodeTypes={nodeTypes}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        panOnScroll
        minZoom={0.3}
        maxZoom={1.6}
        onNodeClick={(_, n) => select(selection === n.id ? null : n.id)}
        onPaneClick={() => select(null)}
        colorMode="dark"
      >
        <Background variant={BackgroundVariant.Lines} gap={32} lineWidth={1} color="rgba(236,233,226,0.045)" />
        <Fit trigger={`${frame.step}:${built.rows}`} />
      </ReactFlow>
      {selection && <SelectionCard frame={frame} selection={selection} onClose={() => select(null)} />}
    </div>
  )
}

export function EvidenceGraph() {
  return (
    <Panel index="02" title="Evidence graph" aside={<Legend />} className="evid" bodyClass="evid__body">
      <ReactFlowProvider>
        <Inner />
      </ReactFlowProvider>
    </Panel>
  )
}
