import { useEffect, useRef, useState } from 'react'
import * as am5 from '@amcharts/amcharts5'
import * as am5map from '@amcharts/amcharts5/map'
import am5geodata_worldLow from '@amcharts/amcharts5-geodata/worldLow'
import am5themes_Animated from '@amcharts/amcharts5/themes/Animated'
import am5themes_Responsive from '@amcharts/amcharts5/themes/Responsive'

type TraceNode = { account_id: string; pseudonymous_key: string; is_operating_institution: boolean; min_hop: number }
type TraceEdge = { transaction_id: string; source_account: string; destination_account: string; timestamp_utc: string; raw_amount: string; attributed_amount: string; hop: number; channel: string; is_terminal: boolean }
type Trace = { trace_id: string; victim_account: string; seed_transaction_id: string; seed_amount: string; nodes: TraceNode[]; edges: TraceEdge[]; is_synthetic: boolean }
type Flow = TraceEdge & { source_account: string; destination_account: string }

// Schematic display anchors only: the ledger trace contains no account geolocation.
const illustrativeAnchors: [number, number][] = [
  [78.4867, 17.385], [72.8777, 19.076], [77.209, 28.6139], [77.5946, 12.9716],
  [80.2707, 13.0827], [88.3639, 22.5726], [55.2708, 25.2048], [103.8198, 1.3521],
  [72.8777, 19.076], [77.209, 28.6139], [103.8198, 1.3521], [55.2708, 25.2048],
]

export default function MoneyMovementGlobe({ trace, playing, onTogglePlaying, onInspect }: {
  trace: Trace
  playing: boolean
  onTogglePlaying: () => void
  onInspect: (transactionId: string) => void
}) {
  const chartHost = useRef<HTMLDivElement>(null)
  const chartRef = useRef<am5map.MapChart | null>(null)
  const [country, setCountry] = useState('India region')
  const [ready, setReady] = useState(false)
  const flows: Flow[] = [
    ...(trace.nodes.length ? [{ transaction_id: trace.seed_transaction_id, source_account: trace.victim_account, destination_account: trace.nodes.find(node => node.min_hop === 1)?.account_id ?? trace.nodes[0].account_id, timestamp_utc: '', raw_amount: trace.seed_amount, attributed_amount: trace.seed_amount, hop: 0, channel: 'Reported payment', is_terminal: false }] : []),
    ...trace.edges,
  ]

  useEffect(() => {
    if (!chartHost.current) return
    const root = am5.Root.new(chartHost.current)
    const responsive = am5themes_Responsive.new(root)
    root.setThemes([am5themes_Animated.new(root), responsive])

    const chart = root.container.children.push(am5map.MapChart.new(root, {
      projection: am5map.geoOrthographic(),
      panX: 'rotateX',
      panY: 'rotateY',
      wheelY: 'zoom',
      wheelX: 'none',
      minZoomLevel: 0.85,
      maxZoomLevel: 9,
      homeZoomLevel: 1.05,
      homeGeoPoint: { longitude: 78, latitude: 19 },
      autoHome: true,
      paddingTop: 12,
      paddingRight: 12,
      paddingBottom: 12,
      paddingLeft: 12,
    }))
    chartRef.current = chart

    const polygons = chart.series.push(am5map.MapPolygonSeries.new(root, { geoJSON: am5geodata_worldLow }))
    polygons.mapPolygons.template.setAll({
      fill: am5.color(0xe2eee8),
      fillOpacity: 0.92,
      stroke: am5.color(0xffffff),
      strokeWidth: 0.8,
      interactive: true,
      tooltipText: '{name}',
      cursorOverStyle: 'pointer',
    })
    polygons.mapPolygons.template.states.create('hover', { fill: am5.color(0xb9d8c9) })
    polygons.mapPolygons.template.states.create('active', { fill: am5.color(0x4b9579) })
    polygons.mapPolygons.template.events.on('click', event => {
      const polygon = event.target
      const data = polygon.dataItem
      if (!data) return
      const name = String((data.dataContext as { name?: string }).name ?? 'Selected country')
      setCountry(name)
      chart.series.each(series => { if (series instanceof am5map.MapPolygonSeries) series.mapPolygons.each(item => item.set('active', false)) })
      polygon.set('active', true)
      const centroid = am5map.getGeoCentroid(data)
      chart.zoomToGeoPoint(centroid, 2.8, true)
    })

    const graticule = chart.series.unshift(am5map.GraticuleSeries.new(root, {}))
    graticule.mapLines.template.setAll({ stroke: am5.color(0x9ebcaf), strokeOpacity: 0.22, strokeWidth: 0.7 })

    const routeSeries = chart.series.push(am5map.MapLineSeries.new(root, {}))
    routeSeries.mapLines.template.setAll({ stroke: am5.color(0x3e9878), strokeOpacity: 0.72, strokeWidth: 2.2, interactive: true, cursorOverStyle: 'pointer' })
    routeSeries.mapLines.template.events.on('click', event => {
      const transactionId = (event.target.dataItem?.dataContext as { transactionId?: string } | undefined)?.transactionId
      if (typeof transactionId === 'string') onInspect(transactionId)
    })

    const points = chart.series.push(am5map.MapPointSeries.new(root, {}))
    points.bullets.push((bulletRoot, _series, dataItem) => {
      const data = dataItem.dataContext as { terminal?: boolean; title?: string; transactionId?: string }
      const terminal = Boolean(data.terminal)
      const container = am5.Container.new(bulletRoot, { interactive: true, cursorOverStyle: 'pointer', tooltipText: '{title}' })
      container.children.push(am5.Circle.new(bulletRoot, {
        radius: terminal ? 6 : 5,
        fill: am5.color(terminal ? 0xc86e5e : 0x398d70),
        stroke: am5.color(0xffffff),
        strokeWidth: 2,
        shadowColor: am5.color(terminal ? 0xc86e5e : 0x398d70),
        shadowBlur: 9,
        shadowOpacity: 0.45,
      }))
      const label = String(data.title ?? '')
      container.children.push(am5.Label.new(bulletRoot, {
        text: label,
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
        if (typeof transactionId === 'string') onInspect(transactionId)
      })
      return am5.Bullet.new(bulletRoot, { sprite: container })
    })

    const movement = chart.series.push(am5map.MapPointSeries.new(root, {}))
    movement.bullets.push(bulletRoot => am5.Bullet.new(bulletRoot, {
      sprite: am5.Circle.new(bulletRoot, { radius: 3.7, fill: am5.color(0x74d4aa), stroke: am5.color(0xffffff), strokeWidth: 1, shadowColor: am5.color(0x48a37f), shadowBlur: 12, shadowOpacity: 0.8 }),
    }))

    const zoom = chart.set('zoomControl', am5map.ZoomControl.new(root, {}))
    zoom.homeButton.set('visible', true)
    zoom.homeButton.events.on('click', () => {
      setCountry('India region')
      chart.goHome(900)
    })

    // Reuse the trace hops at illustrative places; the ledger does not contain account geolocation.
    const nodeIds = new Set([trace.victim_account, ...trace.nodes.map(node => node.account_id)])
    const nodePosition = new Map<string, [number, number]>()
    let nodeIndex = 0
    nodeIds.forEach(id => { nodePosition.set(id, illustrativeAnchors[nodeIndex % illustrativeAnchors.length]); nodeIndex += 1 })
    routeSeries.data.setAll(flows.flatMap((flow, index) => {
      const start = nodePosition.get(flow.source_account)
      const end = nodePosition.get(flow.destination_account)
      if (!start || !end) return []
      return [{ geometry: { type: 'LineString' as const, coordinates: [start, end] }, transactionId: flow.transaction_id, index }]
    }))
    points.data.setAll(Array.from(nodePosition.entries()).map(([id, position], index) => {
      const node = trace.nodes.find(item => item.account_id === id)
      const source = id === trace.victim_account
      const flow = source ? flows[0] : flows.find(item => item.source_account === id || item.destination_account === id)
      const terminal = Boolean(node && !node.is_operating_institution)
      return { id, geometry: { type: 'Point' as const, coordinates: position }, title: source ? 'Reported source · schematic' : `${terminal ? 'Institution boundary' : `Hop ${node?.min_hop ?? index}`} · schematic`, terminal, transactionId: flow?.transaction_id }
    }))
    chart.appear(900, 100)
    polygons.events.on('datavalidated', () => {
      if (!chart.get('homeGeoPoint')) chart.goHome(0)
      setReady(true)
    })

    return () => {
      chartRef.current = null
      root.dispose()
    }
  }, [trace.trace_id, onInspect])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const routes = chart.series.values.find(series => series instanceof am5map.MapLineSeries) as am5map.MapLineSeries | undefined
    const movement = chart.series.values.find(series => series instanceof am5map.MapPointSeries && series.dataItems.length > 0 && series.bullets.length > 0) as am5map.MapPointSeries | undefined
    if (!routes || !movement) return
    const items = movement.dataItems
    const routeItems = routes.dataItems
    if (!playing) {
      items.forEach(item => item.set('visible', false))
      return
    }
    items.forEach((item, index) => {
      item.set('visible', true)
      const route = routeItems[index % Math.max(1, routeItems.length)]
      if (!route) return
      item.set('lineDataItem', route)
      item.animate({ key: 'positionOnLine', from: 0, to: 1, duration: 3800 + index * 400, loops: Infinity, easing: am5.ease.linear })
    })
  }, [playing, ready, trace.trace_id])

  return <div className="money-globe-shell">
    <div className="money-globe-topline"><span><i className="globe-live-dot"/> {country.toUpperCase()}</span><span className="globe-schematic-tag">SCHEMATIC MOVEMENT · NOT GEOGRAPHIC EVIDENCE</span></div>
    <div className="money-globe-chart" ref={chartHost} aria-label="Interactive globe centered on India showing schematic transaction movement"/>
    <div className="money-globe-footer">
      <div><span className="globe-key-dot source-dot"/> Reported source <span className="globe-key-dot hop-dot"/> Ledger hop <span className="globe-key-dot boundary-dot"/> Institution boundary</div>
      <button type="button" onClick={onTogglePlaying} aria-label={playing ? 'Pause money movement' : 'Play money movement'}>{playing ? 'Ⅱ Pause movement' : '▶ Resume movement'}</button>
      <small>Route positions are schematic across India; account locations are not supplied by this trace.</small>
    </div>
    {!ready && <div className="globe-loading">Loading country map…</div>}
  </div>
}
