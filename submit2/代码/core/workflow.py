from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from . import eastmoney, push, report, scoring


def run_workflow(
    config: dict[str, Any],
    log: Callable[[str], None] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    base_dir: str | None = None,
) -> dict[str, Any]:
    log = log or (lambda _: None)
    board = config["board"]
    scoring_cfg = config["scoring"]
    weights = scoring_cfg["weights"]

    log(f"开始抓取东方财富 {board['name']}（{board['code']}）成分股...")
    stocks = eastmoney.fetch_board_constituents(board["code"])
    total = len(stocks)
    log(f"共获取 {total} 只成分股，开始抓取新闻提及...")

    news_map = eastmoney.fetch_news_counts(
        stocks,
        page_size=int(scoring_cfg.get("news_page_size", 30)),
        news_days=int(scoring_cfg.get("news_days", 1)),
        news_link_count=int(scoring_cfg.get("news_link_count", 3)),
        progress=progress,
    )
    eastmoney.attach_news(stocks, news_map)
    log("新闻数据已合并，开始计算综合热度分...")

    ranked = scoring.compute_scores(stocks, weights)
    top_n = int(scoring_cfg.get("top_n", 10))
    top = ranked[:top_n]
    for index, stock in enumerate(top, start=1):
        stock["rank"] = index
        stock["summary"] = scoring.make_summary(
            stock, index, board_name=board["name"]
        )

    run_at = datetime.now(eastmoney.BEIJING_TZ)
    markdown = report.build_markdown(
        top,
        board_code=board["code"],
        board_name=board["name"],
        total_count=total,
        weights=weights,
        run_at=run_at,
    )
    plain_text = report.build_plain_text(top, board["name"], run_at=run_at)
    report_path = report.save_report(markdown, top, base_dir or ".")
    log(f"报告已生成：{report_path}")

    outcomes = push.push_all(
        config["push"],
        markdown=markdown,
        plain_text=plain_text,
        title=f"{board['name']} 概念热度榜 {run_at:%Y-%m-%d}",
    )
    for outcome in outcomes:
        log(f"[{outcome.channel}] {outcome.message}")
    if not outcomes:
        log("未启用推送渠道，仅保存本地报告。")

    return {
        "top_stocks": top,
        "total_count": total,
        "markdown": markdown,
        "plain_text": plain_text,
        "report_path": str(report_path),
        "push_outcomes": outcomes,
        "run_at": run_at,
    }
