export interface StrategyMeta { key: string; name: string; style: string; description: string; colors: Record<string, string> }
export interface Condition { name: string; passed: boolean | null; detail: string; weight: number }
export interface Signal { date: string; type: 'buy' | 'sell' | 'info'; label: string; price: number }
export interface StrategyResult {
  strategy: string; symbol: string; state: string; score: number; signal: string
  conditions: Condition[]; signals: Signal[]; levels: Record<string, number | null>
  notes: string[]; overlays: Record<string, { time: string; value: number }[]>; last_signal: Signal | null
}
export interface Fundamentals {
  name?: string | null; industry?: string | null; market_cap?: number | null; rev_yoy?: number | null; eps_yoy?: number | null
  rev_yoy_prev?: number | null; eps_yoy_prev?: number | null; eps_accel?: boolean | null; eps_qoq?: number | null; rev_qoq?: number | null
  margin?: number | null; roe?: number | null; trailing_pe?: number | null; forward_pe?: number | null; fwd_eps_growth?: number | null
  inst_pct?: number | null; short_pct?: number | null; next_earnings?: string | null; days_to_earnings?: number | null
  quarters?: { period: string; revenue: number | null; eps: number | null; net_income: number | null }[]
}
export interface Candle { time: string; open: number; high: number; low: number; close: number; volume: number }
export interface StockResponse {
  symbol: string; candles: Candle[]; result: StrategyResult
  summary: { key: string; name: string; state: string; score: number; signal: string }[]
  rs: number | null; sector: string | null; sector_rank: number | null; sector_total: number | null
  market: { stage: number | null }
  fundamentals: Fundamentals | null
}
export interface Row {
  symbol: string; state?: string; score?: number; signal?: string; close?: number; chg1d?: number
  rs?: number | null; sector?: string | null; passed?: number; total?: number; error?: string
  last_signal?: Signal | null; updated?: string
  eps_yoy?: number | null; rev_yoy?: number | null; market_cap?: number | null; days_to_earnings?: number | null
  industry?: string | null
}
export interface NewsItem { title: string; url: string | null; source: string; time: string | null; kind: 'news' | 'filing'; via: string; tags: string[]; items?: string[] }
export interface SectorInfo { sector: string; rank: number | null; rs_score: number | null; count: number }
export interface ConsensusRow {
  symbol: string; close: number; chg1d: number; rs: number | null; sector: string | null; industry?: string | null; eps_yoy?: number | null; rev_yoy?: number | null
  days_to_earnings?: number | null; support: number; fresh_buys: number; score: number
  strategies: Record<string, { signal: string; score: number; state: string; last_signal: Signal | null; supports: boolean }>
}
export interface ScanStatus { running: boolean; phase: string; done: number; total: number; error: string | null; finished: number | null }
export interface Trade { entry_date: string; exit_date: string; entry: number; exit: number; stop: number; ret: number; r: number; bars: number; reason: string }
export interface Backtest {
  symbol: string; start: string; end: string; trades: number; win_rate: number | null; avg_win: number | null
  avg_loss: number | null; avg_r: number | null; profit_factor: number | null; total_return: number; buy_hold: number
  max_drawdown: number; avg_bars: number | null; trade_list: Trade[]
  open_trade: { entry_date: string; entry: number; stop: number; ret: number; bars: number } | null
  equity: { time: string; value: number }[]
}
export interface MarketIdx { close: number; chg1d: number; above50: boolean; above200: boolean; above21ema: boolean; golden: boolean; stage: number | null; off_high: number; ret1m: number | null; ret3m: number | null }
export interface Market { regime?: 'bull' | 'neutral' | 'bear'; SPY?: MarketIdx; QQQ?: MarketIdx; breadth: { count: number; pct_above_50?: number; pct_above_200?: number; pct_near_high?: number } }

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init)
  if (!r.ok) {
    let msg = r.statusText
    try { msg = (await r.json()).detail ?? msg } catch { /* ignore */ }
    throw new Error(msg)
  }
  return r.json()
}

export const api = {
  strategies: () => j<StrategyMeta[]>('/api/strategies'),
  market: () => j<Market>('/api/market'),
  watchlist: (strategy: string) => j<Row[]>(`/api/watchlist?strategy=${strategy}`),
  addWatch: (s: string) => j<{ watchlist: string[] }>(`/api/watchlist/${encodeURIComponent(s)}`, { method: 'POST' }),
  delWatch: (s: string) => j<{ watchlist: string[] }>(`/api/watchlist/${encodeURIComponent(s)}`, { method: 'DELETE' }),
  stock: (s: string, strategy: string, days = 400) => j<StockResponse>(`/api/stock/${encodeURIComponent(s)}?strategy=${strategy}&days=${days}`),
  backtest: (s: string, strategy: string, days = 750) => j<Backtest>(`/api/backtest/${encodeURIComponent(s)}?strategy=${strategy}&days=${days}`),
  scan: (strategy: string, minScore = 0) => j<{ rows: Row[]; total: number; status: ScanStatus }>(`/api/scan?strategy=${strategy}&min_score=${minScore}&limit=1000`),
  news: (s: string) => j<{ symbol: string; items: NewsItem[]; total: number }>(`/api/news/${encodeURIComponent(s)}`),
  sectors: () => j<SectorInfo[]>('/api/sectors'),
  consensus: (min: number, mode: 'buyhold' | 'score') => j<{ rows: ConsensusRow[]; total: number; status: ScanStatus }>(`/api/consensus?min_support=${min}&mode=${mode}`),
  scanRun: () => j<{ started: boolean; status: ScanStatus }>('/api/scan/run', { method: 'POST' }),
  scanStatus: () => j<ScanStatus>('/api/scan/status'),
  search: (q: string) => j<string[]>(`/api/search?q=${encodeURIComponent(q)}`),
}

export const pct = (v: number | null | undefined, nd = 1) => (v == null ? '–' : `${(v * 100).toFixed(nd)}%`)
export const cap = (v: number | null | undefined) => (v == null ? '–' : v >= 1e12 ? `${(v / 1e12).toFixed(2)}T` : v >= 1e9 ? `${(v / 1e9).toFixed(1)}B` : `${(v / 1e6).toFixed(0)}M`)
export const ago = (iso: string | null | undefined) => {
  if (!iso) return '–'
  const ms = Date.now() - new Date(iso).getTime()
  const h = ms / 3.6e6
  if (h < 1) return `${Math.max(1, Math.round(ms / 6e4))} 分钟前`
  if (h < 24) return `${Math.round(h)} 小时前`
  const d = h / 24
  if (d < 7) return `${Math.round(d)} 天前`
  return iso.slice(5, 10).replace('-', '/')
}
export const num = (v: number | null | undefined, nd = 2) => (v == null ? '–' : v.toFixed(nd))
