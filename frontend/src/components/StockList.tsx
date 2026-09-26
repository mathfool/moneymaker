import { useEffect, useState } from 'react'
import { api, pct, num, daysAgo, type Row, type ScanStatus, type ConsensusRow, type SectorInfo, type Position, type MarketFlag } from '../api'

interface Props {
  strategy: string
  selected: string | null
  onSelect: (s: string) => void
  refreshKey: number
  positions: Position[]
  onPositionsChange: (p: Position[]) => void
  market: MarketFlag | null
  onMarket: (m: MarketFlag) => void
}

const STRAT_NAMES: Record<string, string> = { minervini: 'Minervini', weinstein: 'Weinstein', kullamagi: 'Kullamägi', kell: 'Kell', jlaw: 'J Law', consensus: '共识' }

function Badge({ r, blocking }: { r: Row; blocking?: boolean }) {
  if (r.error) return <span className="badge none">无数据</span>
  const s = r.signal ?? 'none'
  if (s === 'buy' && blocking) return <span className="badge none" title="大盘过滤：SPY 在 50 日线下方，买入信号只作观察">买入·大盘过滤</span>
  if (s === 'hold' && r.last_signal?.type === 'buy') {
    const d = daysAgo(r.last_signal.date)
    if (d <= 4) return <span className="badge buy" title="买点在 3 个交易日内，还可以跟进">买点 {d} 天前</span>
    return <span className="badge hold" title="买点已超过 3 个交易日，不追">持有</span>
  }
  const label = s === 'buy' ? '买入' : s === 'sell' ? '卖出' : s === 'hold' ? '持有' : '观望'
  return <span className={`badge ${s}`}>{label}</span>
}

function PositionItem({ p, selected, onSelect, onDelete }: { p: Position; selected: boolean; onSelect: () => void; onDelete: () => void }) {
  const a = p.advice
  const color = a?.action === '离场' ? 'var(--red)' : a?.action === '持有' ? 'var(--green)' : 'var(--yellow)'
  return (
    <div className={`row ${selected ? 'selected' : ''}`} onClick={onSelect}>
      <div className="sym">{p.symbol} <span style={{ color: 'var(--muted)', fontSize: 11, fontWeight: 400 }}>{p.shares} 股 @ {p.cost} · {STRAT_NAMES[p.strategy] ?? p.strategy}</span></div>
      <div className="price">
        {p.close != null && <>{num(p.close)} <span className={(p.pnl_pct ?? 0) >= 0 ? 'up' : 'down'}>{pct(p.pnl_pct)}</span></>}
        <button className="del" title="删除持仓" onClick={e => { e.stopPropagation(); onDelete() }}>×</button>
      </div>
      <div className="state">
        <span className="badge" style={{ background: 'transparent', border: `1px solid ${color}`, color }}>{a?.action ?? '?'}</span>
        <span>{p.pnl != null ? `${p.pnl >= 0 ? '+' : ''}$${p.pnl.toFixed(0)}` : ''} · {p.days} 天</span>
      </div>
      {a?.reason && <div className="state" style={{ marginTop: -2, whiteSpace: 'normal' }}>{a.reason}</div>}
    </div>
  )
}

function AddPosition({ strategy, onAdd }: { strategy: string; onAdd: (p: Position[]) => void }) {
  const [sym, setSym] = useState(''); const [shares, setShares] = useState(''); const [cost, setCost] = useState('')
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10)); const [strat, setStrat] = useState(strategy)
  const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false)
  const submit = async () => {
    if (!sym || !shares || !cost) { setErr('代码、股数、成本都要填'); return }
    setBusy(true)
    try { const r = await api.addPosition({ symbol: sym, shares: Number(shares), cost: Number(cost), date, strategy: strat }); onAdd(r.positions); setSym(''); setShares(''); setCost(''); setErr(null) }
    catch (e) { setErr(String((e as Error).message ?? e)) } finally { setBusy(false) }
  }
  return (
    <div className="progress" style={{ flexWrap: 'wrap', gap: 6 }}>
      <input style={{ width: 64 }} placeholder="代码" value={sym} onChange={e => setSym(e.target.value.toUpperCase())} />
      <input style={{ width: 56 }} placeholder="股数" type="number" value={shares} onChange={e => setShares(e.target.value)} />
      <input style={{ width: 64 }} placeholder="成本" type="number" value={cost} onChange={e => setCost(e.target.value)} />
      <input style={{ width: 118 }} type="date" value={date} onChange={e => setDate(e.target.value)} />
      <select value={strat} onChange={e => setStrat(e.target.value)} title="用哪个策略的规则管理这笔持仓">
        {Object.entries(STRAT_NAMES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
      <button className="primary" onClick={submit} disabled={busy}>{busy ? '…' : '添加'}</button>
      {err && <span className="err" style={{ padding: 0 }}>{err}</span>}
    </div>
  )
}

function RowItem({ r, selected, onSelect, onDelete, blocking }: { r: Row; selected: boolean; onSelect: () => void; onDelete?: () => void; blocking?: boolean }) {
  return (
    <div className={`row ${selected ? 'selected' : ''}`} onClick={onSelect}>
      <div className="sym">{r.symbol} {r.rs != null && <span className="badge none" title="RS 相对强度排名">RS {r.rs}</span>} {r.industry && <span style={{ color: 'var(--muted)', fontSize: 10.5, fontWeight: 400 }}>{r.industry}</span>}</div>
      <div className="price">
        {r.close != null && <>{num(r.close)} <span className={(r.chg1d ?? 0) >= 0 ? 'up' : 'down'}>{pct(r.chg1d)}</span></>}
        {onDelete && <button className="del" title="移出自选" onClick={e => { e.stopPropagation(); onDelete() }}>×</button>}
      </div>
      <div className="state">
        <Badge r={r} blocking={blocking} />
        <span className="scorebar" title={`设置完成度 ${r.score ?? 0}%`}><i style={{ width: `${r.score ?? 0}%` }} /></span>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.error ?? r.state}</span>
      </div>
      {(r.eps_yoy != null || r.rev_yoy != null) && (
        <div className="state" style={{ marginTop: -2 }}>
          <span>EPS <b className={(r.eps_yoy ?? 0) >= 0.25 ? 'up' : (r.eps_yoy ?? 0) < 0 ? 'down' : ''}>{pct(r.eps_yoy, 0)}</b></span>
          <span>营收 <b className={(r.rev_yoy ?? 0) >= 0.20 ? 'up' : (r.rev_yoy ?? 0) < 0 ? 'down' : ''}>{pct(r.rev_yoy, 0)}</b></span>
          {r.days_to_earnings != null && r.days_to_earnings >= 0 && r.days_to_earnings <= 7 && <span style={{ color: 'var(--yellow)' }}>⚠ {r.days_to_earnings}天后财报</span>}
        </div>
      )}
      {r.last_signal && (
        <div className="state" style={{ marginTop: -2 }}>
          <span style={{ color: r.last_signal.type === 'buy' ? 'var(--green)' : 'var(--red)' }}>
            最近{r.last_signal.type === 'buy' ? '买' : '卖'} {r.last_signal.date} @{num(r.last_signal.price)} · {r.last_signal.label}
          </span>
        </div>
      )}
    </div>
  )
}

const SHORT: Record<string, string> = { minervini: 'M', weinstein: 'W', kullamagi: 'K', kell: 'O', jlaw: 'J', consensus: 'C' }
const FULL: Record<string, string> = { minervini: 'Minervini', weinstein: 'Weinstein', kullamagi: 'Kullamägi', kell: 'Kell', jlaw: 'J Law', consensus: '共识' }

function ConsensusItem({ r, selected, onSelect }: { r: ConsensusRow; selected: boolean; onSelect: () => void }) {
  return (
    <div className={`row ${selected ? 'selected' : ''}`} onClick={onSelect}>
      <div className="sym">{r.symbol} {r.rs != null && <span className="badge none">RS {r.rs}</span>} {r.industry && <span style={{ color: 'var(--muted)', fontSize: 10.5, fontWeight: 400 }}>{r.industry}</span>}</div>
      <div className="price">{num(r.close)} <span className={(r.chg1d ?? 0) >= 0 ? 'up' : 'down'}>{pct(r.chg1d)}</span></div>
      <div className="state">
        <span className="badge hold">{r.support}/5 支持</span>
        {Object.entries(r.strategies).map(([k, v]) => (
          <span key={k} className={`badge ${v.supports ? (v.signal === 'buy' ? 'buy' : 'hold') : 'none'}`}
            title={`${FULL[k]}：${v.state}（${Math.round(v.score)} 分${v.last_signal ? `，最近${v.last_signal.type === 'buy' ? '买' : '卖'} ${v.last_signal.date}` : ''}）`}>{SHORT[k]}</span>
        ))}
      </div>
      <div className="state" style={{ marginTop: -2 }}>
        <span>EPS <b className={(r.eps_yoy ?? 0) >= 0.25 ? 'up' : (r.eps_yoy ?? 0) < 0 ? 'down' : ''}>{pct(r.eps_yoy, 0)}</b></span>
        <span>营收 <b className={(r.rev_yoy ?? 0) >= 0.2 ? 'up' : (r.rev_yoy ?? 0) < 0 ? 'down' : ''}>{pct(r.rev_yoy, 0)}</b></span>
        {r.fresh_buys > 0 && <span className="up">今日 {r.fresh_buys} 个买入信号</span>}
      </div>
    </div>
  )
}

const SECTOR_CN: Record<string, string> = {
  'Information Technology': '信息技术', 'Health Care': '医疗保健', 'Financials': '金融', 'Consumer Discretionary': '可选消费',
  'Communication Services': '通信服务', 'Industrials': '工业', 'Consumer Staples': '必需消费', 'Energy': '能源',
  'Materials': '材料', 'Real Estate': '房地产', 'Utilities': '公用事业', 'Unknown': '未分类',
}
const secName = (s: string | null | undefined) => (s ? SECTOR_CN[s] ?? s : '未分类')

function SectorFilter({ sectors, sector, industry, industries, onSector, onIndustry }: {
  sectors: SectorInfo[]; sector: string; industry: string; industries: string[]; onSector: (s: string) => void; onIndustry: (s: string) => void
}) {
  return (
    <div className="progress">
      <select value={sector} onChange={e => { onSector(e.target.value); onIndustry('') }} style={{ maxWidth: 150 }}>
        <option value="">全部板块</option>
        {sectors.map(s => <option key={s.sector} value={s.sector}>{s.rank ? `#${s.rank} ` : ''}{secName(s.sector)} ({s.count})</option>)}
      </select>
      <select value={industry} onChange={e => onIndustry(e.target.value)} style={{ maxWidth: 120 }} disabled={industries.length === 0}>
        <option value="">全部行业</option>
        {industries.map(i => <option key={i} value={i}>{i}</option>)}
      </select>
    </div>
  )
}

export default function StockList({ strategy, selected, onSelect, refreshKey, positions, onPositionsChange, market, onMarket }: Props) {
  const blocking = !!market?.blocking
  const [sectors, setSectors] = useState<SectorInfo[]>([])
  const [sector, setSector] = useState(() => localStorage.getItem('mm_sector') ?? '')
  const [industry, setIndustry] = useState(() => localStorage.getItem('mm_industry') ?? '')
  useEffect(() => { api.sectors().then(setSectors).catch(() => {}) }, [refreshKey])
  useEffect(() => { localStorage.setItem('mm_sector', sector); localStorage.setItem('mm_industry', industry) }, [sector, industry])
  const secOk = (r: { sector?: string | null; industry?: string | null }) =>
    (!sector || (r.sector ?? 'Unknown') === sector) && (!industry || r.industry === industry)
  const [tab, setTab] = useState<'watch' | 'scan' | 'consensus' | 'positions'>(() => (localStorage.getItem('mm_tab') as 'watch') ?? 'watch')
  useEffect(() => { localStorage.setItem('mm_tab', tab) }, [tab])
  const [cons, setCons] = useState<ConsensusRow[]>([])
  const [consMin, setConsMin] = useState(() => Number(localStorage.getItem('mm_cons_min') ?? 3))
  const [consMode, setConsMode] = useState<'buyhold' | 'score'>(() => (localStorage.getItem('mm_cons_mode') as 'buyhold' | 'score') ?? 'buyhold')
  useEffect(() => { localStorage.setItem('mm_cons_min', String(consMin)); localStorage.setItem('mm_cons_mode', consMode) }, [consMin, consMode])
  const loadCons = async () => { try { setCons((await api.consensus(consMin, consMode)).rows) } catch (e) { setErr(String(e)) } }
  useEffect(() => { loadCons() }, [consMin, consMode, refreshKey]) // eslint-disable-line react-hooks/exhaustive-deps
  const [watch, setWatch] = useState<Row[]>([])
  const [scan, setScan] = useState<Row[]>([])
  const [status, setStatus] = useState<ScanStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<string[]>([])
  const [err, setErr] = useState<string | null>(null)
  const [minScore, setMinScore] = useState(60)
  const [onlyBuy, setOnlyBuy] = useState(false)
  const [fundOn, setFundOn] = useState(() => localStorage.getItem('mm_fund') === '1')
  const [epsMin, setEpsMin] = useState(() => Number(localStorage.getItem('mm_eps') ?? 25))
  const [revMin, setRevMin] = useState(() => Number(localStorage.getItem('mm_rev') ?? 10))
  useEffect(() => { localStorage.setItem('mm_fund', fundOn ? '1' : '0'); localStorage.setItem('mm_eps', String(epsMin)); localStorage.setItem('mm_rev', String(revMin)) }, [fundOn, epsMin, revMin])

  const loadWatch = async () => {
    setLoading(true)
    try { const r = await api.watchlist(strategy); setWatch(r.rows); onMarket(r.market); setErr(null) } catch (e) { setErr(String(e)) } finally { setLoading(false) }
  }
  const loadScan = async () => {
    try { const r = await api.scan(strategy); setScan(r.rows); setStatus(r.status); onMarket(r.market) } catch (e) { setErr(String(e)) }
  }

  useEffect(() => { loadWatch(); loadScan() }, [strategy, refreshKey]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!status?.running) return
    const t = setInterval(async () => {
      const s = await api.scanStatus()
      setStatus(s)
      if (!s.running) { loadScan(); loadWatch(); loadCons() }
    }, 2000)
    return () => clearInterval(t)
  }, [status?.running]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (q.length < 1) { setHits([]); return }
    const t = setTimeout(() => api.search(q).then(setHits).catch(() => setHits([])), 150)
    return () => clearTimeout(t)
  }, [q])

  const add = async (s: string) => {
    setQ(''); setHits([])
    try { await api.addWatch(s); await loadWatch(); onSelect(s.toUpperCase()); setTab('watch') } catch (e) { setErr(String(e)) }
  }
  const del = async (s: string) => { await api.delWatch(s); loadWatch() }
  const runScan = async () => { const r = await api.scanRun(); setStatus(r.status) }

  const fundOk = (r: Row) => !fundOn || ((r.eps_yoy ?? -1) >= epsMin / 100 && (r.rev_yoy ?? -1) >= revMin / 100)
  const scanRows = scan.filter(r => (r.score ?? 0) >= minScore && (!onlyBuy || r.signal === 'buy' || r.signal === 'hold') && fundOk(r) && secOk(r))
  const consRows = cons.filter(secOk)
  const industries = Array.from(new Set([...scan, ...cons].filter(r => !sector || (r.sector ?? 'Unknown') === sector).map(r => r.industry).filter((x): x is string => !!x))).sort()
  const sectorFilter = <SectorFilter sectors={sectors} sector={sector} industry={industry} industries={industries} onSector={setSector} onIndustry={setIndustry} />

  return (
    <aside className="sidebar">
      <div className="section search" style={{ borderBottom: '1px solid var(--border)' }}>
        <input
          style={{ width: '100%' }} placeholder="输入代码添加到自选，回车确认" value={q}
          onChange={e => setQ(e.target.value.toUpperCase())}
          onKeyDown={e => { if (e.key === 'Enter' && q) add(q) }}
        />
        {hits.length > 0 && <div className="dd">{hits.map(h => <div key={h} onMouseDown={() => add(h)}>{h}</div>)}</div>}
      </div>
      <div className="tabs">
        <button className={tab === 'watch' ? 'active' : ''} onClick={() => setTab('watch')}>自选 ({watch.length})</button>
        <button className={tab === 'scan' ? 'active' : ''} onClick={() => setTab('scan')}>扫描 ({scanRows.length})</button>
        <button className={tab === 'consensus' ? 'active' : ''} onClick={() => setTab('consensus')}>共识 ({consRows.length})</button>
        <button className={tab === 'positions' ? 'active' : ''} onClick={() => setTab('positions')}>持仓 ({positions.length})</button>
      </div>
      {blocking && <div className="progress" style={{ color: 'var(--yellow)' }}>⚠ 大盘过滤：SPY 在 50 日线下方，买入信号只作观察</div>}
      {err && <div className="err">{err}</div>}
      {tab === 'watch' && (
        <div className="list">
          {loading && watch.length === 0 && <div className="empty">加载中…</div>}
          {watch.map(r => <RowItem key={r.symbol} r={r} selected={r.symbol === selected} onSelect={() => onSelect(r.symbol)} onDelete={() => del(r.symbol)} blocking={blocking} />)}
        </div>
      )}
      {tab === 'positions' && (
        <>
          <AddPosition strategy={strategy} onAdd={onPositionsChange} />
          <div className="list">
            {positions.length === 0 && <div className="empty">录入你实际持有的票，软件会按你选的策略告诉你该持有还是离场</div>}
            {positions.map(p => <PositionItem key={p.symbol} p={p} selected={p.symbol === selected} onSelect={() => onSelect(p.symbol)} onDelete={async () => onPositionsChange((await api.delPosition(p.symbol)).positions)} />)}
            {positions.length > 0 && (
              <div className="progress" style={{ borderTop: '1px solid var(--border)', borderBottom: 0 }}>
                合计市值 ${positions.reduce((a, p) => a + (p.value ?? 0), 0).toFixed(0)} · 浮动 <span className={positions.reduce((a, p) => a + (p.pnl ?? 0), 0) >= 0 ? 'up' : 'down'}>${positions.reduce((a, p) => a + (p.pnl ?? 0), 0).toFixed(0)}</span>
              </div>
            )}
          </div>
        </>
      )}
      {tab === 'consensus' && (
        <>
          <div className="progress">
            <label>≥ <select value={consMin} onChange={e => setConsMin(Number(e.target.value))}>{[2, 3, 4, 5].map(n => <option key={n} value={n}>{n}</option>)}</select> 个策略</label>
            <select value={consMode} onChange={e => setConsMode(e.target.value as 'buyhold' | 'score')} style={{ marginLeft: 8 }}>
              <option value="buyhold">给出买入或持有</option>
              <option value="score">设置分数 ≥ 70</option>
            </select>
          </div>
          {sectorFilter}
          <div className="progress" style={{ color: 'var(--yellow)' }}>回测提示：多策略同时"持有"多半说明行情已走了一段，并不比单策略信号更准。优先看有"今日买入信号"的。</div>
          <div className="list">
            {consRows.length === 0 && <div className="empty">{scan.length ? '没有满足条件的股票' : '请先扫描全市场'}</div>}
            {consRows.map(r => <ConsensusItem key={r.symbol} r={r} selected={r.symbol === selected} onSelect={() => onSelect(r.symbol)} />)}
          </div>
        </>
      )}
      {tab === 'scan' && (
        <>
          <div className="progress">
            {status?.running ? (
              <>
                <span>{status.phase === 'prices' ? '下载行情' : status.phase === 'fundamentals' ? '拉取基本面' : status.phase === 'strategies' ? '计算策略' : status.phase}</span>
                <span className="bar"><i style={{ width: status.total ? `${(100 * status.done) / status.total}%` : '0%' }} /></span>
                <span>{status.done}/{status.total}</span>
              </>
            ) : (
              <>
                <button onClick={runScan}>扫描 S&P500 + NDX100</button>
                <span style={{ marginLeft: 'auto' }}>{status?.finished ? `更新于 ${new Date(status.finished * 1000).toLocaleTimeString()}` : scan[0]?.updated ? `缓存 ${scan[0].updated.slice(0, 16).replace('T', ' ')}` : '尚未扫描'}</span>
              </>
            )}
          </div>
          <div className="progress">
            <label>分数 ≥ <input type="number" style={{ width: 52 }} value={minScore} min={0} max={100} onChange={e => setMinScore(Number(e.target.value))} /></label>
            <label style={{ marginLeft: 8 }}><input type="checkbox" checked={onlyBuy} onChange={e => setOnlyBuy(e.target.checked)} /> 只看买入/持有</label>
          </div>
          {sectorFilter}
          <div className="progress" title="最新季度同比增速，数据来自 Yahoo Finance">
            <label><input type="checkbox" checked={fundOn} onChange={e => setFundOn(e.target.checked)} /> 基本面</label>
            <label>EPS ≥ <input type="number" style={{ width: 48 }} value={epsMin} onChange={e => setEpsMin(Number(e.target.value))} />%</label>
            <label>营收 ≥ <input type="number" style={{ width: 48 }} value={revMin} onChange={e => setRevMin(Number(e.target.value))} />%</label>
          </div>
          <div className="list">
            {scanRows.length === 0 && <div className="empty">{scan.length ? '没有满足筛选的股票' : '点击上方按钮扫描全市场'}</div>}
            {scanRows.map(r => <RowItem key={r.symbol} r={r} selected={r.symbol === selected} onSelect={() => onSelect(r.symbol)} blocking={blocking} />)}
          </div>
        </>
      )}
    </aside>
  )
}
