import { useEffect, useRef } from 'react'
import {
  createChart, ColorType, CrosshairMode, LineStyle, type IChartApi, type ISeriesApi, type SeriesMarker, type Time,
} from 'lightweight-charts'
import type { Candle, Signal } from '../api'

interface Props {
  candles: Candle[]
  overlays: Record<string, { time: string; value: number }[]>
  colors: Record<string, string>
  signals: Signal[]
  levels: Record<string, number | null>
  equity?: { time: string; value: number }[]
}

const LEVEL_STYLE: Record<string, { color: string; title: string }> = {
  stop: { color: '#ef5350', title: '止损' },
  pivot: { color: '#f5a623', title: '枢轴' },
  flag_high: { color: '#f5a623', title: '旗形高点' },
  base_high: { color: '#f5a623', title: '平台高点' },
  resistance: { color: '#f5a623', title: '阻力' },
}

export default function Chart({ candles, overlays, colors, signals, levels }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const linesRef = useRef<ISeriesApi<'Line'>[]>([])
  const priceLinesRef = useRef<ReturnType<ISeriesApi<'Candlestick'>['createPriceLine']>[]>([])

  useEffect(() => {
    if (!ref.current) return
    const chart = createChart(ref.current, {
      layout: { background: { type: ColorType.Solid, color: '#0f1115' }, textColor: '#8b93a7', fontSize: 11 },
      grid: { vertLines: { color: '#1a1f29' }, horzLines: { color: '#1a1f29' } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#262c38', scaleMargins: { top: 0.05, bottom: 0.22 } },
      timeScale: { borderColor: '#262c38', rightOffset: 6 },
      autoSize: true,
    })
    const cs = chart.addCandlestickSeries({
      upColor: '#26a69a', downColor: '#ef5350', borderVisible: false, wickUpColor: '#26a69a', wickDownColor: '#ef5350',
    })
    const vol = chart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'vol' })
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
    chartRef.current = chart
    seriesRef.current = cs
    volRef.current = vol
    return () => { chart.remove(); chartRef.current = null; seriesRef.current = null; volRef.current = null; linesRef.current = []; priceLinesRef.current = [] }
  }, [])

  useEffect(() => {
    const chart = chartRef.current, cs = seriesRef.current, vol = volRef.current
    if (!chart || !cs || !vol) return
    cs.setData(candles.map(c => ({ time: c.time as Time, open: c.open, high: c.high, low: c.low, close: c.close })))
    vol.setData(candles.map(c => ({ time: c.time as Time, value: c.volume, color: c.close >= c.open ? 'rgba(38,166,154,.45)' : 'rgba(239,83,80,.45)' })))
    linesRef.current.forEach(l => chart.removeSeries(l))
    linesRef.current = []
    const first = candles[0]?.time
    for (const [name, pts] of Object.entries(overlays)) {
      const s = chart.addLineSeries({ color: colors[name] ?? '#888', lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
      s.setData(pts.filter(p => !first || p.time >= first).map(p => ({ time: p.time as Time, value: p.value })))
      linesRef.current.push(s)
    }
    const markers: SeriesMarker<Time>[] = signals
      .filter(s => !first || s.date >= first)
      .map(s => ({
        time: s.date as Time,
        position: s.type === 'buy' ? 'belowBar' : 'aboveBar',
        color: s.type === 'buy' ? '#26a69a' : '#ef5350',
        shape: s.type === 'buy' ? 'arrowUp' : 'arrowDown',
        text: s.label,
      }))
    cs.setMarkers(markers)
    priceLinesRef.current.forEach(p => cs.removePriceLine(p))
    priceLinesRef.current = []
    for (const [k, v] of Object.entries(levels)) {
      const st = LEVEL_STYLE[k]
      if (!st || v == null) continue
      priceLinesRef.current.push(cs.createPriceLine({ price: v, color: st.color, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: st.title }))
    }
    chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, candles.length - 180), to: candles.length + 5 })
  }, [candles, overlays, colors, signals, levels])

  return (
    <div className="chart-wrap">
      <div className="legend">
        {Object.keys(overlays).map(n => <span key={n}><i style={{ background: colors[n] ?? '#888' }} />{n}</span>)}
        <span><i style={{ background: '#ef5350' }} />虚线 = 止损 / 枢轴</span>
      </div>
      <div ref={ref} style={{ position: 'absolute', inset: 0 }} />
    </div>
  )
}
