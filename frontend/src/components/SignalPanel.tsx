import { useEffect, useState } from 'react'
import { api, num, pct, cap, type Backtest, type StockResponse, type StrategyMeta } from '../api'

interface Props {
  data: StockResponse | null
  strategy: StrategyMeta | undefined
  onPickStrategy: (k: string) => void
  onShowEquity?: (eq: Backtest['equity'] | null) => void
}

const LEVEL_NAMES: Record<string, string> = {
  stop: '止损位', pivot: '枢轴 / 突破点', sma50: '50 日均线', resistance: '基底阻力', ma30w: '30 周均线',
  flag_high: '旗形高点', ema10: 'EMA10', ema20: 'EMA20', ema21: 'EMA21', base_high: '平台高点',
}

export default function SignalPanel({ data, strategy, onPickStrategy }: Props) {
  const [account, setAccount] = useState(() => Number(localStorage.getItem('mm_account') ?? 100000))
  const [riskPct, setRiskPct] = useState(() => Number(localStorage.getItem('mm_risk') ?? 0.5))
  const [bt, setBt] = useState<Backtest | null>(null)
  const [btLoading, setBtLoading] = useState(false)

  useEffect(() => { localStorage.setItem('mm_account', String(account)); localStorage.setItem('mm_risk', String(riskPct)) }, [account, riskPct])
  useEffect(() => { setBt(null) }, [data?.symbol, data?.result.strategy])

  if (!data || !strategy) return <aside className="rightpanel"><div className="empty">选择一只股票</div></aside>
  const r = data.result
  const f = data.fundamentals
  const g = (v: number | null | undefined, thr: number) => (v == null ? '' : v >= thr ? 'up' : v < 0 ? 'down' : '')
  const close = data.candles[data.candles.length - 1]?.close
  const stop = r.levels.stop
  const riskAmt = account * riskPct / 100
  const perShare = stop != null && close ? close - stop : null
  const shares = perShare && perShare > 0 ? Math.floor(riskAmt / perShare) : null

  const runBt = async () => {
    setBtLoading(true)
    try { setBt(await api.backtest(data.symbol, r.strategy)) } finally { setBtLoading(false) }
  }

  return (
    <aside className="rightpanel">
      <div className="section">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div className="score-ring" style={{ color: r.score >= 75 ? 'var(--green)' : r.score >= 50 ? 'var(--yellow)' : 'var(--muted)' }}>{Math.round(r.score)}</div>
          <div>
            <div style={{ fontWeight: 600 }}>{r.state}</div>
            <div className="muted" style={{ color: 'var(--muted)', fontSize: 11.5 }}>{strategy.name} · {strategy.style}</div>
          </div>
          <span className={`badge ${r.signal}`} style={{ marginLeft: 'auto', fontSize: 12 }}>
            {r.signal === 'buy' ? '今日买入信号' : r.signal === 'sell' ? '今日卖出信号' : r.signal === 'hold' ? '持有中' : '观望'}
          </span>
        </div>
        <p style={{ color: 'var(--muted)', fontSize: 12, lineHeight: 1.5, margin: '10px 0 0' }}>{strategy.description}</p>
      </div>

      <div className="section">
        <h3>五种策略一览</h3>
        <div className="chips">
          {data.summary.map(s => (
            <div key={s.key} className={`chip ${s.key === r.strategy ? 'active' : ''}`} onClick={() => onPickStrategy(s.key)} title={s.state}>
              <b>{s.name}</b>
              <span className={`badge ${s.signal}`} style={{ marginRight: 4 }}>{Math.round(s.score)}</span>{s.state.length > 14 ? s.state.slice(0, 14) + '…' : s.state}
            </div>
          ))}
        </div>
      </div>

      <div className="section">
        <h3>条件检查</h3>
        {r.conditions.map((c, i) => (
          <div className="cond" key={i}>
            <span className={`ic ${c.passed == null ? 'na' : c.passed ? 'ok' : 'no'}`}>{c.passed == null ? '?' : c.passed ? '✓' : '✗'}</span>
            <div>
              <div>{c.name}</div>
              {c.detail && <div className="detail">{c.detail}</div>}
            </div>
          </div>
        ))}
      </div>

      <div className="section">
        <h3>关键价位 & 仓位</h3>
        <div className="kv">
          <span className="k">现价</span><span>{num(close)}</span>
          {Object.entries(r.levels).map(([k, v]) => v != null && <span key={k} style={{ display: 'contents' }}><span className="k">{LEVEL_NAMES[k] ?? k}</span><span>{num(v)}{k === 'stop' && close ? ` (${pct(v / close - 1)})` : ''}</span></span>)}
          <span className="k">RS 排名 / 板块</span><span>{data.rs ?? '–'} / {data.sector ?? '–'}{data.sector_rank ? ` #${data.sector_rank}/${data.sector_total}` : ''}</span>
        </div>
        <div className="calc" style={{ marginTop: 10 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <label>账户 $<input type="number" value={account} onChange={e => setAccount(Number(e.target.value))} /></label>
            <label>风险 <input type="number" step={0.1} value={riskPct} onChange={e => setRiskPct(Number(e.target.value))} />%</label>
          </div>
          <div className="kv">
            <span className="k">单笔可亏</span><span>${riskAmt.toFixed(0)}</span>
            <span className="k">每股风险</span><span>{perShare != null ? num(perShare) : '–'}</span>
            <span className="k">建议股数</span><span style={{ fontWeight: 600 }}>{shares ?? '–'} 股{shares && close ? ` ≈ $${(shares * close).toFixed(0)} (${pct(shares * close / account, 0)})` : ''}</span>
          </div>
        </div>
      </div>

      <div className="section">
        <h3>基本面 {f?.name && <span style={{ textTransform: 'none', letterSpacing: 0 }}>· {f.name}</span>}</h3>
        {!f ? <div style={{ color: 'var(--muted)' }}>暂无数据</div> : (
          <>
            {f.days_to_earnings != null && f.days_to_earnings >= 0 && f.days_to_earnings <= 7 && (
              <div style={{ color: 'var(--yellow)', marginBottom: 6 }}>⚠ {f.days_to_earnings} 天后财报（{f.next_earnings}），财报前建仓有跳空风险</div>
            )}
            <div className="kv">
              <span className="k">最新季 EPS 同比</span><span className={g(f.eps_yoy, 0.25)}>{pct(f.eps_yoy, 0)}{f.eps_yoy_prev != null ? ` (上季 ${pct(f.eps_yoy_prev, 0)})` : ''}{f.eps_accel ? ' ↑加速' : ''}</span>
              <span className="k">最新季营收同比</span><span className={g(f.rev_yoy, 0.20)}>{pct(f.rev_yoy, 0)}{f.rev_yoy_prev != null ? ` (上季 ${pct(f.rev_yoy_prev, 0)})` : ''}</span>
              <span className="k">净利率 / ROE</span><span>{pct(f.margin, 0)} / {pct(f.roe, 0)}</span>
              <span className="k">预期 EPS 增速（前瞻/追溯）</span><span className={g(f.fwd_eps_growth, 0.20)}>{pct(f.fwd_eps_growth, 0)}</span>
              <span className="k">PE 追溯 / 前瞻</span><span>{num(f.trailing_pe, 1)} / {num(f.forward_pe, 1)}</span>
              <span className="k">市值 / 机构持股 / 空头</span><span>{cap(f.market_cap)} / {pct(f.inst_pct, 0)} / {pct(f.short_pct, 1)}</span>
              <span className="k">下次财报</span><span>{f.next_earnings ?? '–'}{f.days_to_earnings != null ? `（${f.days_to_earnings} 天）` : ''}</span>
            </div>
            {f.quarters && f.quarters.length > 0 && (
              <table className="trades" style={{ marginTop: 8 }}>
                <thead><tr><th>季度</th><th>营收</th><th>EPS</th><th>净利</th></tr></thead>
                <tbody>
                  {f.quarters.slice(0, 6).map(q => <tr key={q.period}><td>{q.period}</td><td>{cap(q.revenue)}</td><td>{num(q.eps)}</td><td>{cap(q.net_income)}</td></tr>)}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>

      <div className="section">
        <h3>信号历史（近 400 交易日）</h3>
        <div className="sig-list">
          {r.signals.length === 0 && <div style={{ color: 'var(--muted)' }}>无信号</div>}
          {[...r.signals].reverse().map((s, i) => (
            <div className="sig" key={i}>
              <span><span className={`badge ${s.type}`}>{s.type === 'buy' ? '买' : '卖'}</span> {s.date}</span>
              <span>{s.label} @ {num(s.price)}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="section">
        <h3>回测（近 3 年，全仓进出，止损按策略）</h3>
        {!bt && <button onClick={runBt} disabled={btLoading}>{btLoading ? '计算中…' : `回测 ${strategy.name} 在 ${data.symbol} 上的表现`}</button>}
        {bt && (
          <>
            <div className="bt-grid">
              <div className="cell"><b>交易数</b><span>{bt.trades}</span></div>
              <div className="cell"><b>胜率</b><span>{pct(bt.win_rate, 0)}</span></div>
              <div className="cell"><b>平均 R</b><span>{bt.avg_r ?? '–'}</span></div>
              <div className="cell"><b>盈亏比 PF</b><span>{bt.profit_factor ?? '–'}</span></div>
              <div className="cell"><b>平均盈利</b><span className="up">{pct(bt.avg_win)}</span></div>
              <div className="cell"><b>平均亏损</b><span className="down">{pct(bt.avg_loss)}</span></div>
              <div className="cell"><b>策略收益</b><span className={bt.total_return >= 0 ? 'up' : 'down'}>{pct(bt.total_return, 0)}</span></div>
              <div className="cell"><b>买入持有</b><span>{pct(bt.buy_hold, 0)}</span></div>
              <div className="cell"><b>最大回撤</b><span className="down">{pct(bt.max_drawdown, 0)}</span></div>
            </div>
            {bt.open_trade && <div style={{ marginTop: 8, fontSize: 12 }}>持仓中：{bt.open_trade.entry_date} @{bt.open_trade.entry}，浮动 {pct(bt.open_trade.ret)}，止损 {bt.open_trade.stop}</div>}
            <table className="trades" style={{ marginTop: 8 }}>
              <thead><tr><th>入场</th><th>出场</th><th>收益</th><th>R</th><th>天</th><th>原因</th></tr></thead>
              <tbody>
                {[...bt.trade_list].reverse().map((t, i) => (
                  <tr key={i}><td>{t.entry_date}</td><td>{t.exit_date}</td><td className={t.ret >= 0 ? 'up' : 'down'}>{pct(t.ret)}</td><td>{t.r}</td><td>{t.bars}</td><td>{t.reason}</td></tr>
                ))}
              </tbody>
            </table>
            <button style={{ marginTop: 8 }} onClick={runBt}>重新计算</button>
          </>
        )}
      </div>

      <div className="section">
        <h3>交易者提示</h3>
        <ul className="notes">{r.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
      </div>
    </aside>
  )
}
