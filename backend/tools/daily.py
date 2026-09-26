"""每日收盘后作业：扫描全市场 + 自选，汇总当天新出的买卖信号，发 macOS 通知并写日报。

用法:
  .venv/bin/python tools/daily.py            # 跑扫描 + 通知
  .venv/bin/python tools/daily.py --no-scan  # 只用上次扫描结果生成日报（调试用）
  .venv/bin/python tools/daily.py --test     # 不扫描，发一条测试通知，验证通知能弹出来

可选环境变量（都不设就只发系统通知 + 写日报）:
  MM_TELEGRAM_TOKEN / MM_TELEGRAM_CHAT_ID   Telegram 机器人推送
  MM_MIN_SCORE (默认 70)   扫描池买入信号的最低分数
  MM_MIN_RS    (默认 50)   扫描池买入信号的最低 RS（回测里 RS<50 的信号全部亏钱）
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db, scanner, watchlist, market, positions, settings  # noqa: E402
from app.config import DATA_DIR  # noqa: E402
from app.strategies import STRATEGIES  # noqa: E402

MIN_SCORE = float(os.environ.get("MM_MIN_SCORE", 70))
# Kell 的三种买点互斥，条件全过也只有 65 分，所以单独给一个门槛（60 = 均线多头 + 未过度延伸 + 买点）
MIN_SCORE_BY = {"kell": min(MIN_SCORE, 60.0)}
SHORT = {"minervini": "M", "weinstein": "W", "kullamagi": "K", "kell": "O", "jlaw": "J", "consensus": "C"}
MIN_RS = int(os.environ.get("MM_MIN_RS", 50))
REPORT_DIR = DATA_DIR / "reports"
NAMES = {k: s.name for k, s in STRATEGIES.items()}


def notify(title: str, body: str) -> None:
    """macOS 通知中心 + 可选 Telegram。"""
    safe_body = body.replace('"', "'")[:230]
    safe_title = title.replace('"', "'")
    try:
        subprocess.run(["osascript", "-e", f'display notification "{safe_body}" with title "{safe_title}" sound name "Glass"'],
                       check=False, timeout=10)
    except Exception as e:  # noqa: BLE001
        print("osascript failed:", e)
    tok, chat = os.environ.get("MM_TELEGRAM_TOKEN"), os.environ.get("MM_TELEGRAM_CHAT_ID")
    if tok and chat:
        try:
            import requests
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          json={"chat_id": chat, "text": f"{title}\n{body}"[:4000]}, timeout=15)
        except Exception as e:  # noqa: BLE001
            print("telegram failed:", e)


def build_report() -> tuple[str, str, int]:
    """返回 (通知短文本, 日报 markdown, 信号总数)。"""
    watch = watchlist.load()
    latest = None
    rows_by_strategy = {k: db.load_scan(k) for k in STRATEGIES}
    for rows in rows_by_strategy.values():
        for r in rows:
            ls = r.get("last_signal")
            if ls and (latest is None or ls["date"] > latest):
                latest = ls["date"]
    today = latest or datetime.now().strftime("%Y-%m-%d")

    watch_hits: list[tuple[str, str, str, dict]] = []      # (symbol, strategy, buy/sell, row)
    scan_buys: dict[str, list[dict]] = {k: [] for k in STRATEGIES}
    for k, rows in rows_by_strategy.items():
        for r in rows:
            ls = r.get("last_signal")
            if not ls or ls["date"] != today:
                continue
            if r["symbol"] in watch:
                watch_hits.append((r["symbol"], k, ls["type"], r))
            if ls["type"] == "buy" and (r.get("score") or 0) >= MIN_SCORE_BY.get(k, MIN_SCORE) and (r.get("rs") or 0) >= MIN_RS:
                scan_buys[k].append(r)

    m = market.market_summary()
    spy = m.get("SPY", {})
    regime = {"bull": "牛市结构", "neutral": "中性", "bear": "熊市结构"}.get(m.get("regime", ""), "?")

    lines = [f"# MoneyMaker 日报 {today}", "",
             f"大盘：{regime}，SPY {spy.get('close')} ({spy.get('chg1d', 0) * 100:+.2f}%)，"
             f"50日线{'上' if spy.get('above50') else '下'}方，200日线{'上' if spy.get('above200') else '下'}方，Stage {spy.get('stage')}", ""]
    short: list[str] = []
    lines.append("## 自选股信号")
    if watch_hits:
        for sym, k, typ, r in sorted(watch_hits, key=lambda x: (x[2] != "buy", x[0])):
            ls = r["last_signal"]
            tag = "买入" if typ == "buy" else "卖出"
            lines.append(f"- **{sym}** {tag} · {NAMES[k]} · {ls['label']} @ {ls['price']} · RS {r.get('rs')} · {r.get('state')}")
            short.append(f"{sym} {tag}({SHORT[k]})")
    else:
        lines.append("- 无")
    lines.append("")
    lines.append(f"## 扫描池新买入信号（分数 ≥ {MIN_SCORE:.0f}，Kell ≥ {MIN_SCORE_BY['kell']:.0f}，RS ≥ {MIN_RS}）")
    n_scan = 0
    for k, rows in scan_buys.items():
        if not rows:
            continue
        rows.sort(key=lambda r: (r.get("score") or 0, r.get("rs") or 0), reverse=True)
        lines.append(f"### {NAMES[k]}（{len(rows)}）")
        for r in rows[:15]:
            ls = r["last_signal"]
            eps = r.get("eps_yoy")
            lines.append(f"- {r['symbol']} · {ls['label']} @ {ls['price']} · 分 {r.get('score')} · RS {r.get('rs')} · "
                         f"{r.get('sector') or ''}" + (f" · EPS {eps * 100:+.0f}%" if eps is not None else ""))
        n_scan += len(rows)
    if n_scan == 0:
        lines.append("- 无")
    lines.append("")
    lines.append("## 我的持仓")
    pos = positions.enriched()
    if pos:
        for p in pos:
            a = p.get("advice") or {}
            lines.append(f"- **{p['symbol']}** {p['shares']:.0f} 股 @ {p['cost']} → {p.get('close')}，"
                         f"{(p.get('pnl_pct') or 0) * 100:+.1f}%（{p.get('pnl', 0):+.0f} 美元）· **{a.get('action', '?')}** · {a.get('reason', '')}")
            if a.get("action") == "离场":
                short.insert(0, f"持仓 {p['symbol']} 规则要求离场")
    else:
        lines.append("- 未录入持仓（左侧\"持仓\"标签可以添加）")
    lines.append("")
    st = settings.load()
    spy_ok = bool(spy.get("above50"))
    if st.get("market_filter") and not spy_ok:
        lines.insert(3, "> ⚠ 大盘过滤已开启，SPY 在 50 日线下方：以下买入信号只作观察，不开新仓。")
    lines.append("## 自选股持仓状态（M=Minervini W=Weinstein K=Kullamägi O=Kell J=J Law C=共识）")
    for sym in watch:
        parts = []
        for k, rows in rows_by_strategy.items():
            r = next((x for x in rows if x["symbol"] == sym), None)
            if r:
                parts.append(f"{SHORT[k]}:{ {'buy': '买', 'sell': '卖', 'hold': '持', 'none': '观'}.get(r.get('signal'), '?') }")
        lines.append(f"- {sym}  " + " ".join(parts))

    n_total = len(watch_hits) + n_scan
    head = f"自选 {len(watch_hits)} 个信号，扫描池 {n_scan} 个买点" if n_total else "今天没有新信号"
    body = "；".join(short[:6]) if short else (f"扫描池：" + "，".join(
        f"{NAMES[k]} {len(v)}" for k, v in scan_buys.items() if v) if n_scan else f"大盘 {regime}")
    return f"{head} · {body}", "\n".join(lines), n_total


def main() -> None:
    args = sys.argv[1:]
    if "--test" in args:
        notify("MoneyMaker 测试通知", "如果你看到这条，定时任务的通知是通的。")
        print("test notification sent")
        return
    if "--no-scan" not in args:
        print("scanning…", flush=True)
        scanner.run_scan(watchlist.load())
        if scanner.status.get("error"):
            notify("MoneyMaker 扫描失败", scanner.status["error"])
            sys.exit(1)
    short, report, n = build_report()
    REPORT_DIR.mkdir(exist_ok=True)
    day = report.split("\n", 1)[0].split()[-1]
    path = REPORT_DIR / f"{day}.md"
    path.write_text(report)
    print(report)
    notify(f"MoneyMaker {day}", short)
    print(f"\nreport -> {path}")


if __name__ == "__main__":
    main()
