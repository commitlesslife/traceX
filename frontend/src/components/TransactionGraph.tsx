import { useEffect, useMemo, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'

type TraceNode = {
  account_id: string
  pseudonymous_key: string
  institution_id: string
  unmoved_traced_value: string
  min_hop: number
  is_terminal: boolean
}
type TraceEdge = {
  transaction_id: string
  source_account: string
  destination_account: string
  attributed_amount: string
  hop: number
  is_terminal: boolean
}
type Trace = {
  trace_id: string
  is_synthetic: boolean
  victim_account: string
  seed_transaction_id: string
  seed_amount: string
  nodes: TraceNode[]
  edges: TraceEdge[]
}

const money = (value: string) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(value))
const compact = (value: string) => value.length > 20 ? `${value.slice(0, 17)}…` : value
const initials = (value: string) => value.split(/[ _-]/).map(part => part[0]).join('').slice(0, 2).toUpperCase()
const clamp = (value: number) => Math.min(2.5, Math.max(0.25, value))

export default function TransactionGraph({ trace, onInspect, playing }: { trace: Trace; onInspect: (id: string) => void; playing: boolean }) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ x: number; y: number; left: number; top: number } | null>(null)
  const [zoom, setZoom] = useState(1)

  const edges = useMemo(() => {
    const first = trace.nodes.find(node => node.min_hop === 1) ?? trace.nodes[0]
    const seed: TraceEdge[] = first ? [{
      transaction_id: trace.seed_transaction_id,
      source_account: trace.victim_account,
      destination_account: first.account_id,
      attributed_amount: trace.seed_amount,
      hop: 0,
      is_terminal: false,
    }] : []
    return [...seed, ...trace.edges]
  }, [trace])

  const layout = useMemo(() => {
    const nodeMap = new Map(trace.nodes.map(node => [node.account_id, node]))
    const ids = [trace.victim_account, ...trace.nodes.map(node => node.account_id)].filter((id, index, all) => all.indexOf(id) === index)
    const levels = new Map<string, number>([[trace.victim_account, 0]])
    edges.forEach(edge => {
      levels.set(edge.source_account, Math.min(levels.get(edge.source_account) ?? 99, edge.hop))
      levels.set(edge.destination_account, Math.min(levels.get(edge.destination_account) ?? 99, edge.hop + 1))
    })
    const maxLevel = Math.max(1, ...levels.values())
    const groups = Array.from({ length: maxLevel + 1 }, (_, level) => ids.filter(id => (levels.get(id) ?? nodeMap.get(id)?.min_hop ?? 1) === level))
    const width = Math.max(940, groups.length * 252)
    const height = Math.max(430, ...groups.map(group => group.length * 126 + 80))
    const positions = new Map<string, { x: number; y: number }>()
    groups.forEach((group, level) => group.forEach((id, index) => {
      positions.set(id, { x: 110 + level * (width - 220) / maxLevel, y: height * (index + 1) / (group.length + 1) })
    }))
    return { ids, nodeMap, positions, width, height }
  }, [trace, edges])

  useEffect(() => {
    const viewport = viewportRef.current
    if (!viewport) return
    const fitWidth = (viewport.clientWidth - 36) / layout.width
    setZoom(clamp(Math.max(0.6, Math.min(1, fitWidth))))
    viewport.scrollTo({ left: 0, top: 0 })
  }, [trace.trace_id, layout.width])

  const zoomTo = (next: number, anchorX?: number, anchorY?: number) => {
    const viewport = viewportRef.current
    if (!viewport) return
    const target = clamp(next)
    const x = anchorX ?? viewport.clientWidth / 2
    const y = anchorY ?? viewport.clientHeight / 2
    const old = zoom
    const left = (viewport.scrollLeft + x) * target / old - x
    const top = (viewport.scrollTop + y) * target / old - y
    setZoom(target)
    requestAnimationFrame(() => viewport.scrollTo({ left, top }))
  }

  useEffect(() => {
    const viewport = viewportRef.current
    if (!viewport) return
    const handleWheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return
      event.preventDefault()
      const bounds = viewport.getBoundingClientRect()
      zoomTo(zoom * (event.deltaY < 0 ? 1.12 : 1 / 1.12), event.clientX - bounds.left, event.clientY - bounds.top)
    }
    viewport.addEventListener('wheel', handleWheel, { passive: false })
    return () => viewport.removeEventListener('wheel', handleWheel)
  }, [zoom])

  const fitAll = () => {
    const viewport = viewportRef.current
    if (!viewport) return
    const fit = clamp(Math.min((viewport.clientWidth - 32) / layout.width, (viewport.clientHeight - 32) / layout.height))
    setZoom(fit)
    requestAnimationFrame(() => viewport.scrollTo({ left: 0, top: 0 }))
  }

  const edgePath = (edge: TraceEdge) => {
    const source = layout.positions.get(edge.source_account)
    const target = layout.positions.get(edge.destination_account)
    if (!source || !target) return ''
    const bend = Math.max(45, (target.x - source.x) * 0.48)
    return `M ${source.x + 82} ${source.y} C ${source.x + bend} ${source.y}, ${target.x - bend} ${target.y}, ${target.x - 88} ${target.y}`
  }

  const startDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || !viewportRef.current) return
    const target = event.target as Element
    if (target.closest('.original-account-node, .trace-edge-path')) return
    const viewport = viewportRef.current
    dragRef.current = { x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop }
    viewport.setPointerCapture(event.pointerId)
  }
  const moveDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    const viewport = viewportRef.current
    if (!drag || !viewport) return
    viewport.scrollLeft = drag.left - (event.clientX - drag.x)
    viewport.scrollTop = drag.top - (event.clientY - drag.y)
  }
  const endDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    dragRef.current = null
    if (viewportRef.current?.hasPointerCapture(event.pointerId)) viewportRef.current.releasePointerCapture(event.pointerId)
  }

  return <div className="original-graph-wrap">
    <div className="graph-watermark">{trace.is_synthetic ? 'SYNTHETIC FIXTURE' : 'LEDGER TRACE'} <span>·</span> {trace.trace_id}</div>
    <div className="network-zoom-controls" aria-label="Network view controls">
      <span>{Math.round(zoom * 100)}%</span>
      <button type="button" onClick={() => zoomTo(zoom / 1.25)} aria-label="Zoom network out">−</button>
      <button type="button" onClick={() => zoomTo(zoom * 1.25)} aria-label="Zoom network in">+</button>
      <button type="button" onClick={fitAll}>Fit all</button>
      <button type="button" onClick={() => zoomTo(1)}>100%</button>
    </div>
    <div className="graph-scroll" ref={viewportRef} onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag}>
      <div className="graph-artboard" style={{ width: layout.width * zoom, height: layout.height * zoom }}>
      <svg className={`original-trace-graph ${playing ? 'flow-active' : ''}`} viewBox={`0 0 ${layout.width} ${layout.height}`} role="img" aria-label="Scrollable, zoomable transaction flow from reported source through traced accounts">
        <defs>
          <filter id="popShadow" x="-30%" y="-40%" width="160%" height="190%"><feDropShadow dx="0" dy="5" stdDeviation="5" floodColor="#263956" floodOpacity=".14"/></filter>
          <marker id="arrowHead" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0 0 L6 3 L0 6" fill="none" stroke="#578f94" strokeWidth="1.5"/></marker>
        </defs>
        {edges.map(edge => <g key={edge.transaction_id} className="trace-edge-group">
          <path d={edgePath(edge)} className={`trace-edge-path ${edge.is_terminal ? 'is-terminal' : ''}`} markerEnd="url(#arrowHead)" onPointerDown={event => { event.stopPropagation(); if (event.button === 0) onInspect(edge.transaction_id) }}>
            <title>{edge.transaction_id} · {money(edge.attributed_amount)}</title>
          </path>
          <text className="trace-edge-label" x={((layout.positions.get(edge.source_account)?.x ?? 0) + (layout.positions.get(edge.destination_account)?.x ?? 0)) / 2} y={((layout.positions.get(edge.source_account)?.y ?? 0) + (layout.positions.get(edge.destination_account)?.y ?? 0)) / 2 - 11}>{money(edge.attributed_amount)}</text>
          {playing && <circle className="money-particle" r="4"><animateMotion dur={`${3.1 + edge.hop * 0.24}s`} repeatCount="indefinite" path={edgePath(edge)}/></circle>}
        </g>)}
        {layout.ids.map((id, index) => {
          const position = layout.positions.get(id)!
          const node = layout.nodeMap.get(id)
          const source = id === trace.victim_account
          const terminal = Boolean(node?.is_terminal)
          const linked = [...edges].reverse().find(edge => edge.source_account === id || edge.destination_account === id)
          const label = source ? 'Reported source' : node?.pseudonymous_key ?? id
          return <g key={id} className={`original-account-node ${source ? 'source-node' : ''} ${terminal ? 'boundary-node' : ''}`} transform={`translate(${position.x},${position.y})`} aria-hidden="true">
            <title>{label}</title>
            <rect className="node-card-back" x="-83" y="-42" width="166" height="84" rx="12"/>
            <rect className="node-card-face" x="-88" y="-48" width="166" height="84" rx="12" filter="url(#popShadow)"/>
            <circle cx="-65" cy="-25" r="12" className="node-icon-ring"/>
            <text x="-65" y="-21" textAnchor="middle" className="node-icon-text">{source ? '↗' : terminal ? '↗' : initials(node?.institution_id ?? id)}</text>
            <text x="-45" y="-23" className="node-title">{compact(label)}</text>
            <text x="-72" y="-1" className="node-subtitle">{source ? 'VICTIM ACCOUNT' : terminal ? 'OUTSIDE VISIBILITY' : `HOP ${node?.min_hop ?? index}`}</text>
            <text x="-72" y="21" className="node-value">{money(source ? trace.seed_amount : node?.unmoved_traced_value ?? trace.seed_amount)}</text>
            <circle className="node-presence" cx="64" cy="-28" r="4"/>
          </g>
        })}
      </svg>
      {layout.ids.map(id => {
        const position = layout.positions.get(id)!
        const linked = [...edges].reverse().find(edge => edge.source_account === id || edge.destination_account === id)
        const label = id === trace.victim_account ? 'Reported source' : layout.nodeMap.get(id)?.pseudonymous_key ?? id
        return linked && <button key={id} type="button" className="graph-node-hit" style={{ left: (position.x - 88) * zoom, top: (position.y - 48) * zoom, width: 166 * zoom, height: 84 * zoom }} onPointerDown={event => event.stopPropagation()} onClick={() => onInspect(linked.transaction_id)} aria-label={`Inspect transaction for ${label}`} title={`Inspect ${label}`}/>
      })}
      {edges.map(edge => {
        const source = layout.positions.get(edge.source_account)
        const target = layout.positions.get(edge.destination_account)
        if (!source || !target) return null
        const x = (source.x + target.x) / 2
        const y = (source.y + target.y) / 2 - 17
        return <button key={`hit-${edge.transaction_id}`} type="button" className="graph-edge-hit" style={{ left: (x - 40) * zoom, top: (y - 14) * zoom, width: 80 * zoom, height: 28 * zoom }} onPointerDown={event => event.stopPropagation()} onClick={() => onInspect(edge.transaction_id)} aria-label={`Inspect transfer ${edge.transaction_id}`} title={`${edge.transaction_id} · ${money(edge.attributed_amount)}`}/>
      })}
      </div>
    </div>
    <div className="graph-bottom-labels"><span><i className="legend-source"/>Reported source</span><span><i className="legend-internal"/>Ledger account</span><span><i className="legend-outside"/>Boundary</span><small>Scroll to pan · drag empty space · Ctrl + wheel to zoom</small></div>
  </div>
}
