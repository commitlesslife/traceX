import { useEffect, useMemo, useRef, useState } from 'react'
import * as am5 from '@amcharts/amcharts5'
import * as am5map from '@amcharts/amcharts5/map'
import am5geodata_worldLow from '@amcharts/amcharts5-geodata/worldLow'
import am5themes_Responsive from '@amcharts/amcharts5/themes/Responsive'

type TraceNode = { account_id: string; pseudonymous_key: string; institution_id: string; is_operating_institution: boolean; min_hop: number; termination_reason?: string | null }
type TraceEdge = { transaction_id: string; source_account: string; destination_account: string; timestamp_utc: string; raw_amount: string; attributed_amount: string; hop: number; channel: string; is_terminal: boolean }
type Trace = { trace_id: string; victim_account: string; seed_transaction_id: string; seed_amount: string; nodes: TraceNode[]; edges: TraceEdge[]; is_synthetic: boolean }
type Flow = TraceEdge & { source_account: string; destination_account: string }

// Presentation anchors. Ledger records do not supply account geolocation.
const domesticAnchors: [number, number][] = [
  [78.4867, 17.385], [72.8777, 19.076], [77.2090, 28.6139], [77.5946, 12.9716],
  [80.2707, 13.0827], [88.3639, 22.5726], [73.8567, 18.5204], [75.7873, 26.9124],
  [72.5714, 23.0225], [76.6394, 12.2958], [79.0882, 21.1458], [85.1376, 25.5941],
  [74.8723, 31.6340], [73.1812, 22.3072], [76.9558, 11.0168], [80.9462, 26.8467],
  [77.4126, 23.2599], [81.6296, 21.2514], [75.8577, 22.7196], [83.9812, 21.4669],
  [91.7362, 26.1445], [86.2029, 22.8046], [79.4192, 13.6288], [70.8022, 22.3039],
]
const domesticBoundaryAnchors: [number, number][] = [[88.3639, 22.5726], [73.1812, 22.3072]]
const internationalAnchors: [number, number][] = [[55.2708, 25.2048], [103.8198, 1.3521]]
const amount = (value: string) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(value))
const localTime = (value: string) => value ? `${new Date(/[zZ]$|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata' })} IST` : 'Time unavailable'

export default function MoneyMovementGlobe({ trace, playing, onTogglePlaying, onInspect }: {
  trace: Trace
  playing: boolean
  onTogglePlaying: () => void
  onInspect: (transactionId: string) => void
}) {
  const chartHost = useRef<HTMLDivElement>(null)
  const chartRef = useRef<am5map.MapChart | null>(null)
  const movementRef = useRef<am5map.MapPointSeries | null>(null)
  const focusLineRef = useRef<am5map.MapLineSeries | null>(null)
  const focusPointsRef = useRef<am5map.MapPointSeries | null>(null)
  const nodePositionsRef = useRef<Map<string, [number, number]>>(new Map())
  const inspectRef = useRef(onInspect)
  const movementAnimations = useRef<{ stop: () => void }[]>([])
  const [country, setCountry] = useState('India region')
  const [selectedTransfer, setSelectedTransfer] = useState<string | null>(trace.edges[0]?.transaction_id ?? trace.seed_transaction_id)
  const [activeHop, setActiveHop] = useState<number | 'all'>('all')
  const [ready, setReady] = useState(false)
  inspectRef.current = onInspect
  const flows: Flow[] = useMemo(() => [
    ...(trace.nodes.length ? [{ transaction_id: trace.seed_transaction_id, source_account: trace.victim_account, destination_account: trace.nodes.find(node => node.min_hop === 1)?.account_id ?? trace.nodes[0].account_id, timestamp_utc: '', raw_amount: trace.seed_amount, attributed_amount: trace.seed_amount, hop: 0, channel: 'Reported payment', is_terminal: false }] : []),
    ...trace.edges,
  ], [trace])
  const hops = useMemo(() => [...new Set(flows.map(flow => flow.hop))].sort((a, b) => a - b), [flows])
  const visibleFlows = activeHop === 'all' ? flows : flows.filter(flow => flow.hop === activeHop)
  const selectedFlow = flows.find(flow => flow.transaction_id === selectedTransfer) ?? flows[0]
  const sourceNode = trace.nodes.find(node => node.account_id === selectedFlow?.source_account)
  const destinationNode = trace.nodes.find(node => node.account_id === selectedFlow?.destination_account)
  const dense = flows.length > 12

  useEffect(() => {
    setSelectedTransfer(trace.edges[0]?.transaction_id ?? trace.seed_transaction_id)
    setActiveHop('all')
  }, [trace.trace_id, trace.edges, trace.seed_transaction_id])

  useEffect(() => {
    if (!chartHost.current) return
    setReady(false)
    setCountry('India region')
    const root = am5.Root.new(chartHost.current)
    const responsive = am5themes_Responsive.new(root)
    root.setThemes([responsive])

    const chart = root.container.children.push(am5map.MapChart.new(root, {
      projection: am5map.geoOrthographic(),
      panX: 'rotateX',
      panY: 'rotateY',
      wheelY: 'zoom',
      wheelX: 'none',
      pinchZoom: true,
      minZoomLevel: 0.82,
      maxZoomLevel: 5,
      zoomStep: 1.5,
      homeZoomLevel: 0.92,
      homeRotationX: -78,
      homeRotationY: -19,
      rotationX: -78,
      rotationY: -19,
      autoHome: false,
      paddingTop: 12,
      paddingRight: 12,
      paddingBottom: 12,
      paddingLeft: 12,
    }))
    chartRef.current = chart

    const ocean = chart.series.push(am5map.MapPolygonSeries.new(root, {}))
    ocean.mapPolygons.template.setAll({ fill: am5.color(0xd8eaf5), stroke: am5.color(0x9bc7dc), strokeWidth: 1.2, interactive: false })
    ocean.data.push({ geometry: am5map.getGeoRectangle(90, 180, -90, -180) })

    const polygons = chart.series.push(am5map.MapPolygonSeries.new(root, { geoJSON: am5geodata_worldLow }))
    polygons.mapPolygons.template.setAll({
      fill: am5.color(0xb5cbd1),
      fillOpacity: 0.98,
      stroke: am5.color(0xf7fcf8),
      strokeWidth: 0.95,
      interactive: true,
      tooltipText: '{name}',
      cursorOverStyle: 'pointer',
      templateField: 'polygonSettings',
    })
    polygons.events.on('datavalidated', () => {
      chart.goHome(0)
      setReady(true)
    })
    polygons.data.setAll([{ id: 'IN', polygonSettings: { fill: am5.color(0x219277) } }])
    polygons.mapPolygons.template.states.create('hover', { fill: am5.color(0x89accb) })
    polygons.mapPolygons.template.states.create('active', { fill: am5.color(0x5f90b6) })
    polygons.mapPolygons.template.events.on('click', event => {
      const polygon = event.target
      const data = polygon.dataItem
      if (!data) return
      const name = String((data.dataContext as { name?: string }).name ?? 'Selected country')
      setCountry(name)
      polygons.mapPolygons.each(item => item.set('active', false))
      polygon.set('active', true)
      const centroid = am5map.getGeoCentroid(data)
      chart.animate({ key: 'rotationX', to: -centroid.longitude, duration: 650, easing: am5.ease.inOut(am5.ease.cubic) })
      chart.animate({ key: 'rotationY', to: -centroid.latitude, duration: 650, easing: am5.ease.inOut(am5.ease.cubic) })
      chart.animate({ key: 'zoomLevel', to: 1.25, duration: 650, easing: am5.ease.inOut(am5.ease.cubic) })
    })

    const graticule = chart.series.unshift(am5map.GraticuleSeries.new(root, {}))
    graticule.mapLines.template.setAll({ stroke: am5.color(0x76a4c4), strokeOpacity: 0.28, strokeWidth: 0.7 })

    const routeSeries = chart.series.push(am5map.MapLineSeries.new(root, {}))
    routeSeries.mapLines.template.setAll({ stroke: am5.color(0x258b99), strokeOpacity: dense ? 0.34 : 0.8, strokeWidth: dense ? 2 : 3, interactive: true, cursorOverStyle: 'pointer', tooltipText: '{title}' })
    const boundaryRoutes = chart.series.push(am5map.MapLineSeries.new(root, {}))
    boundaryRoutes.mapLines.template.setAll({ stroke: am5.color(0xd46c66), strokeOpacity: dense ? 0.62 : 0.98, strokeWidth: dense ? 2.5 : 3.5, interactive: true, cursorOverStyle: 'pointer', tooltipText: '{title}' })
    const inspectRoute = (event: { target: { dataItem?: { dataContext: unknown } } }) => {
      const transactionId = (event.target.dataItem?.dataContext as { transactionId?: string } | undefined)?.transactionId
      if (typeof transactionId === 'string') { setSelectedTransfer(transactionId); inspectRef.current(transactionId) }
    }
    routeSeries.mapLines.template.events.on('click', inspectRoute)
    boundaryRoutes.mapLines.template.events.on('click', inspectRoute)

    const focusLine = chart.series.push(am5map.MapLineSeries.new(root, {}))
    focusLine.mapLines.template.setAll({ stroke: am5.color(0xf2a34d), strokeOpacity: 1, strokeWidth: 4.5, interactive: false })
    focusLineRef.current = focusLine

    const focusPoints = chart.series.push(am5map.MapPointSeries.new(root, {}))
    focusPoints.bullets.push(bulletRoot => am5.Bullet.new(bulletRoot, {
      sprite: am5.Circle.new(bulletRoot, { radius: 10, fillOpacity: 0, stroke: am5.color(0xf2a34d), strokeWidth: 2.5, shadowColor: am5.color(0xf2a34d), shadowBlur: 12, shadowOpacity: 0.7 }),
    }))
    focusPointsRef.current = focusPoints

    const points = chart.series.push(am5map.MapPointSeries.new(root, {}))
    points.bullets.push((bulletRoot, _series, dataItem) => {
      const data = (dataItem?.dataContext ?? {}) as { source?: boolean; terminal?: boolean; title?: string; label?: string; transactionId?: string }
      const terminal = Boolean(data.terminal)
      const source = Boolean(data.source)
      const container = am5.Container.new(bulletRoot, { interactive: true, cursorOverStyle: 'pointer', tooltipText: '{title}' })
      container.children.push(am5.Circle.new(bulletRoot, {
        radius: terminal || source ? 6.5 : dense ? 3.5 : 4.5,
        fill: am5.color(terminal ? 0xd46c66 : source ? 0x5779c5 : 0x168c85),
        stroke: am5.color(0xffffff),
        strokeWidth: 2,
        shadowColor: am5.color(terminal ? 0xd46c66 : source ? 0x5779c5 : 0x168c85),
        shadowBlur: 9,
        shadowOpacity: 0.45,
      }))
      if (data.label) container.children.push(am5.Label.new(bulletRoot, {
        text: data.label,
        x: 9,
        y: -9,
        fontSize: 10,
        fill: am5.color(0x38544a),
        background: am5.RoundedRectangle.new(bulletRoot, { fill: am5.color(0xffffff), fillOpacity: 0.88, cornerRadiusTL: 4, cornerRadiusTR: 4, cornerRadiusBL: 4, cornerRadiusBR: 4 }),
        paddingLeft: 5,
        paddingRight: 5,
        paddingTop: 3,
        paddingBottom: 3,
      }))
      container.events.on('click', () => {
        const transactionId = data.transactionId
        if (typeof transactionId === 'string') { setSelectedTransfer(transactionId); inspectRef.current(transactionId) }
      })
      return am5.Bullet.new(bulletRoot, { sprite: container })
    })

    const movement = chart.series.push(am5map.MapPointSeries.new(root, {}))
    movementRef.current = movement
    movement.bullets.push((bulletRoot, _series, dataItem) => am5.Bullet.new(bulletRoot, {
      sprite: am5.Circle.new(bulletRoot, { radius: 4.5, fill: am5.color((dataItem?.dataContext as { terminal?: boolean } | undefined)?.terminal ? 0xe68265 : 0x20b6a1), stroke: am5.color(0xffffff), strokeWidth: 1.3, shadowColor: am5.color(0x08764e), shadowBlur: 13, shadowOpacity: 0.9 }),
    }))

    const zoom = chart.set('zoomControl', am5map.ZoomControl.new(root, {}))
    zoom.homeButton.set('visible', true)
    zoom.homeButton.events.on('click', () => {
      setCountry('India region')
      chart.goHome(650)
    })

    // Reuse the trace hops at illustrative places; the ledger does not contain account geolocation.
    const nodePosition = new Map<string, [number, number]>([[trace.victim_account, domesticAnchors[0]]])
    const usedDomestic = new Set([0])
    const rankByHop = new Map<number, number>()
    let placedDomestic = 0
    let domesticBoundaryIndex = 0
    let internationalIndex = 0
    const orderedNodes = [...trace.nodes].sort((a, b) => a.min_hop - b.min_hop || a.account_id.localeCompare(b.account_id))
    orderedNodes.forEach(node => {
      if (node.account_id === trace.victim_account) return
      if (!node.is_operating_institution) {
        const international = node.institution_id === 'INST-INTL-03'
        const anchors = international ? internationalAnchors : domesticBoundaryAnchors
        const index = international ? internationalIndex++ : domesticBoundaryIndex++
        nodePosition.set(node.account_id, anchors[index % anchors.length])
        return
      }
      const rank = rankByHop.get(node.min_hop) ?? 0
      rankByHop.set(node.min_hop, rank + 1)
      let anchorIndex = (node.min_hop * 3 + rank * 7) % domesticAnchors.length
      while (usedDomestic.has(anchorIndex) && usedDomestic.size < domesticAnchors.length) anchorIndex = (anchorIndex + 1) % domesticAnchors.length
      const cycle = Math.floor(placedDomestic / domesticAnchors.length)
      placedDomestic += 1
      usedDomestic.add(anchorIndex)
      const anchor = domesticAnchors[anchorIndex]
      nodePosition.set(node.account_id, cycle ? [anchor[0] + cycle * 0.3, anchor[1] + cycle * 0.25] : anchor)
    })
    nodePositionsRef.current = nodePosition
    flows.forEach((flow, index) => {
      const start = nodePosition.get(flow.source_account)
      const end = nodePosition.get(flow.destination_account)
      if (!start || !end) return
      const series = flow.is_terminal ? boundaryRoutes : routeSeries
      const route = series.pushDataItem({ geometry: { type: 'LineString', coordinates: [start, end] }, transactionId: flow.transaction_id, title: `Hop ${flow.hop} · ${flow.transaction_id}`, index } as am5map.IMapLineSeriesDataItem)
      movement.pushDataItem({ lineDataItem: route, positionOnLine: 0, transactionId: flow.transaction_id, terminal: flow.is_terminal } as am5map.IMapPointSeriesDataItem)
    })
    points.data.setAll(Array.from(nodePosition.entries()).map(([id, position], index) => {
      const node = trace.nodes.find(item => item.account_id === id)
      const source = id === trace.victim_account
      const flow = source ? flows[0] : flows.find(item => item.destination_account === id) ?? flows.find(item => item.source_account === id)
      const terminal = Boolean(node && !node.is_operating_institution)
      return { id, geometry: { type: 'Point' as const, coordinates: position }, title: source ? 'Reported source · schematic' : `${node?.pseudonymous_key ?? id} · ${terminal ? node?.institution_id === 'INST-INTL-03' ? 'International boundary' : 'Domestic institution boundary' : `Hop ${node?.min_hop ?? index}`}`, label: source ? 'SOURCE' : '', source, terminal, transactionId: flow?.transaction_id }
    }))
    return () => {
      movementAnimations.current.forEach(animation => animation.stop())
      movementAnimations.current = []
      chartRef.current = null
      movementRef.current = null
      focusLineRef.current = null
      focusPointsRef.current = null
      nodePositionsRef.current = new Map()
      root.dispose()
    }
  }, [trace.trace_id, flows, trace.nodes, trace.victim_account, dense])

  useEffect(() => {
    const focusLine = focusLineRef.current
    const focusPoints = focusPointsRef.current
    if (!ready || !focusLine || !focusPoints || !selectedFlow) return
    const start = nodePositionsRef.current.get(selectedFlow.source_account)
    const end = nodePositionsRef.current.get(selectedFlow.destination_account)
    if (!start || !end) return
    focusLine.mapLines.template.set('stroke', am5.color(selectedFlow.is_terminal ? 0xe17568 : 0xf0a142))
    focusLine.data.setAll([{ geometry: { type: 'LineString' as const, coordinates: [start, end] } }])
    focusPoints.data.setAll([
      { geometry: { type: 'Point' as const, coordinates: start } },
      { geometry: { type: 'Point' as const, coordinates: end } },
    ])
  }, [ready, selectedFlow])

  useEffect(() => {
    const movement = movementRef.current
    if (!movement || !ready) return
    movementAnimations.current.forEach(animation => animation.stop())
    movementAnimations.current = []
    const items = movement.dataItems
    items.forEach((item, index) => {
      const transactionId = (item.dataContext as { transactionId?: string } | undefined)?.transactionId
      if (!transactionId || !playing || (dense && transactionId !== selectedTransfer)) {
        item.set('visible', false)
        return
      }
      item.set('visible', true)
      const animation = item.animate({ key: 'positionOnLine', from: 0, to: 1, duration: 3300 + index * 260, loops: Infinity, easing: am5.ease.linear })
      if (animation) movementAnimations.current.push(animation)
    })
    return () => {
      movementAnimations.current.forEach(animation => animation.stop())
      movementAnimations.current = []
    }
  }, [playing, ready, trace.trace_id, selectedTransfer, dense])

  return <>
    <div className={`money-globe-shell ${playing ? 'is-playing' : ''}`}>
      <div className="money-globe-topline"><span><i className="globe-live-dot"/> {country.toUpperCase()} <em>DRAG TO ROTATE · SCROLL OR PINCH TO ZOOM</em></span><span className="globe-schematic-tag">SYNTHETIC MAP ANCHORS</span></div>
      <div className="money-globe-chart" ref={chartHost} aria-label="Interactive globe centered on India showing schematic transaction movement"/>
      <div className="globe-route-reel">
        <div className="globe-route-heading"><span>TRACE MOVEMENT <b>{visibleFlows.length} / {flows.length} transfers</b></span><span>SELECT A HOP TO FOCUS</span></div>
        <div className="globe-hop-filters" aria-label="Filter transaction hops">
          <button type="button" className={activeHop === 'all' ? 'active' : ''} onClick={() => setActiveHop('all')}>All hops</button>
          {hops.map(hop => <button type="button" key={hop} className={activeHop === hop ? 'active' : ''} onClick={() => { setActiveHop(hop); setSelectedTransfer(flows.find(flow => flow.hop === hop)?.transaction_id ?? null) }}>{hop === 0 ? 'Reported' : `Hop ${hop}`}</button>)}
        </div>
        <div className="globe-route-track">{visibleFlows.map(flow => <button type="button" key={flow.transaction_id} className={`globe-route-card ${flow.is_terminal ? 'is-boundary' : ''} ${selectedTransfer === flow.transaction_id ? 'is-selected' : ''}`} onClick={() => { setSelectedTransfer(flow.transaction_id); inspectRef.current(flow.transaction_id) }}><span className="globe-route-step"><i/>{flow.hop === 0 ? 'REPORTED' : `HOP ${flow.hop}`}</span><strong>{amount(flow.attributed_amount)}</strong><small>{flow.hop === 0 ? 'Reported payment' : flow.is_terminal ? 'Boundary · attributed' : `${flow.channel || 'Transfer'} · attributed`}</small></button>)}</div>
      </div>
      <div className="money-globe-footer">
        <div><span className="globe-key-dot source-dot"/> Reported source <span className="globe-key-dot hop-dot"/> Ledger hop <span className="globe-key-dot boundary-dot"/> Institution boundary</div>
        <button type="button" onClick={onTogglePlaying} aria-label={playing ? 'Pause money movement' : 'Play money movement'}>{playing ? 'Ⅱ Pause movement' : '▶ Resume movement'}</button>
        <small>Transaction amounts and accounts come from the ledger. Geographic anchors are synthetic.</small>
      </div>
      {!ready && <div className="globe-loading">Loading country map…</div>}
    </div>
    {selectedFlow && <div className="globe-focus-details">
      <div><span>FOCUSED TRANSFER</span><b>{selectedFlow.transaction_id}</b><small>{selectedFlow.hop === 0 ? 'Reported payment' : `Hop ${selectedFlow.hop} · ${selectedFlow.channel}`}</small></div>
      <div><span>ACCOUNT ROUTE</span><b>{sourceNode?.pseudonymous_key ?? selectedFlow.source_account} → {destinationNode?.pseudonymous_key ?? selectedFlow.destination_account}</b><small>{selectedFlow.is_terminal ? destinationNode?.institution_id === 'INST-INTL-03' ? 'Synthetic international processor' : 'External domestic bank' : 'Within operating ledger'}</small></div>
      <div><span>ATTRIBUTED / RAW</span><b>{amount(selectedFlow.attributed_amount)} <i>/</i> {amount(selectedFlow.raw_amount)}</b><small>Victim share / full transfer</small></div>
      <div><span>LEDGER TIME</span><b>{localTime(selectedFlow.timestamp_utc)}</b><small>{selectedFlow.is_terminal ? destinationNode?.termination_reason?.replaceAll('_', ' ') ?? 'Visibility ends at boundary' : 'Transaction evidence available'}</small></div>
      <button type="button" onClick={() => inspectRef.current(selectedFlow.transaction_id)}>Open evidence →</button>
    </div>}
  </>
}
