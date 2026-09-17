import { useEffect, useState } from 'react'
import { api, pct, type Market, type NewsItem, type StockResponse, type StrategyMeta } from './api'
import Chart from './components/Chart'
import StockList from './components/StockList'
import SignalPanel from './components/SignalPanel'

function MarketBar({ m }: { m: Market | null }) {
  if (!m?.SPY) return null
  const regimeLabel = m.regime === 'bull' ? '牛市结构' : m.regime === 'bear' ? '熊市结构' : '中性'
  const idx = (name: 'SPY' | 'QQQ') => {
    const x = m[name]!
    return (
      <span className="pill" title={`Stage ${x.stage} · 距高点 ${pct(x.off_high)} · 1月 ${pct(x.ret1m)} · 3月 ${pct(x.ret3m)}`}>
        {name} {x.close} <span className={x.chg1d >= 0 ? 'up' : 'down'}>{pct(x.chg1d)}</span>
        {' '}<span style={{ color: x.above50 ? 'var(--green)' : 'var(--red)' }}>50日{x.above50 ? '↑' : '↓'}</span>
        {' '}<span style={{ color: x.above200 ? 'var(--green)' : 'var(--red)' }}>200日{x.above200 ? '↑' : '↓'}</span>
      </span>
    )
  }
  return (
    <div className="market">
      <span className={`pill ${m.regime ?? ''}`}>大盘：{regimeLabel} · SPY Stage {m.SPY.stage}</span>
      {idx('SPY')}{m.QQQ && idx('QQQ')}
      {m.breadth?.count > 0 && (
        <span className="pill" title="扫描池内股票">宽度 50日上方 {pct(m.breadth.pct_above_50, 0)} · 200日上方 {pct(m.breadth.pct_above_200, 0)} · 近高点 {pct(m.breadth.pct_near_high, 0)}</span>
      )}
    </div>
  )
}

export default function App() {
  const [strategies, setStrategies] = useState<StrategyMeta[]>([])
  const [strategy, setStrategy] = useState(() => localStorage.getItem('mm_strategy') ?? 'minervini')
  const [symbol, setSymbol] = useState<string | null>(() => localStorage.getItem('mm_symbol'))
  const [data, setData] = useState<StockResponse | null>(null)
  const [market, setMarket] = useState<Market | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [news, setNews] = useState<NewsItem[]>([])
  useEffect(() => {
    if (!symbol) return
    let cancelled = false
    setNews([])
    api.news(symbol).then(r => { if (!cancelled) setNews(r.items) }).catch(() => {})
    return () => { cancelled = true }
  }, [symbol, refreshKey])

  useEffect(() => { api.strategies().then(setStrategies); api.market().then(setMarket).catch(() => {}) }, [])
  useEffect(() => { localStorage.setItem('mm_strategy', strategy) }, [strategy])
  useEffect(() => { if (symbol) localStorage.setItem('mm_symbol', symbol) }, [symbol])

  useEffect(() => {
    if (!symbol) return
    let cancelled = false
    setLoading(true)
    api.stock(symbol, strategy).then(d => { if (!cancelled) { setData(d); setErr(null) } })
      .catch(e => { if (!cancelled) setErr(String(e.message ?? e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [symbol, strategy, refreshKey])

  const meta = strategies.find(s => s.key === strategy)
  const last = data?.candles[data.candles.length - 1]
  const prev = data?.candles[data.candles.length - 2]

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">Money<span>Maker</span></div>
        <div className="strategy-tabs">
          {strategies.map(s => (
            <button key={s.key} className={s.key === strategy ? 'active' : ''} onClick={() => setStrategy(s.key)} title={s.style}>{s.name}</button>
          ))}
        </div>
        <button onClick={() => { setRefreshKey(k => k + 1); api.market().then(setMarket) }} title="重新拉取行情">↻</button>
        <MarketBar m={market} />
      </header>
      <StockList strategy={strategy} selected={symbol} onSelect={setSymbol} refreshKey={refreshKey} />
      <main className="main">
        <div className="chart-header">
          <h2>{symbol ?? '—'}</h2>
          {last && prev && (
            <>
              <span style={{ fontSize: 16 }}>{last.close.toFixed(2)}</span>
              <span className={last.close >= prev.close ? 'up' : 'down'}>{pct(last.close / prev.close - 1)}</span>
              <span className="muted">{last.time}</span>
              {data?.sector && <span className="muted">{data.sector}</span>}
              {data?.rs != null && <span className="badge none">RS {data.rs}</span>}
            </>
          )}
          {loading && <span className="muted">加载中…</span>}
          {err && <span className="err">{err}</span>}
          {data && <span className="muted" style={{ marginLeft: 'auto' }}>{meta?.name}：{data.result.state}</span>}
        </div>
        {data ? (
          <Chart candles={data.candles} overlays={data.result.overlays} colors={meta?.colors ?? {}} signals={data.result.signals} levels={data.result.levels} news={news} />
        ) : (
          <div className="empty" style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{err ?? '在左侧选择一只股票'}</div>
        )}
      </main>
      <SignalPanel data={data} strategy={meta} onPickStrategy={setStrategy} news={news} />
    </div>
  )
}
