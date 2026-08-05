from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _yi(value: float) -> str:
    return f"{value / 1e8:.2f}"


def build_markdown(
    stocks: list[dict[str, Any]],
    board_code: str,
    board_name: str,
    total_count: int,
    weights: dict[str, float],
    run_at: datetime | None = None,
) -> str:
    run_at = run_at or datetime.now()
    lines = [
        f"# {board_name} 概念热度榜 Top{len(stocks)}",
        "",
        f"- 数据日期：{run_at:%Y-%m-%d %H:%M}",
        f"- 数据源：东方财富 {board_name}（{board_code}），共 {total_count} 只成分股",
        (
            "- 综合分 = 成交额 "
            f"{weights.get('turnover', 0):g}% + 涨跌幅 {weights.get('change', 0):g}% "
            f"+ 资金净流入 {weights.get('net_inflow', 0):g}% "
            f"+ 新闻提及 {weights.get('news', 0):g}%（板块内百分位）"
        ),
        "",
        "| 排名 | 代码 | 名称 | 最新价 | 涨跌幅 | 成交额(亿) | 主力净流入(亿) | 新闻 | 综合分 |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for index, stock in enumerate(stocks, start=1):
        lines.append(
            "| "
            f"{index} | {stock['code']} | {stock['name']} | "
            f"{stock.get('price', 0):.2f} | {stock.get('change_pct', 0):+.2f}% | "
            f"{_yi(stock.get('turnover', 0))} | {_yi(stock.get('net_inflow', 0))} | "
            f"{int(stock.get('news_count', 0))} | {stock.get('score', 0):.2f} |"
        )
    lines.append("")
    for index, stock in enumerate(stocks, start=1):
        lines.append(f"## {index}. {stock['name']}（{stock['code']}）")
        lines.append("")
        lines.append(stock.get("summary", ""))
        lines.append("")
        news = stock.get("news") or []
        if news:
            lines.append("关键新闻：")
            for item in news:
                title = item.get("title") or "相关新闻"
                url = item.get("url") or ""
                date_text = item.get("date") or ""
                media = item.get("media") or ""
                suffix = "，".join(part for part in (date_text, media) if part)
                lines.append(f"- [{title}]({url})（{suffix}）")
            lines.append("")
    return "\n".join(lines)


def build_plain_text(
    stocks: list[dict[str, Any]],
    board_name: str,
    run_at: datetime | None = None,
) -> str:
    run_at = run_at or datetime.now()
    lines = [f"{board_name} 概念热度榜 Top{len(stocks)}（{run_at:%Y-%m-%d %H:%M}）", ""]
    for index, stock in enumerate(stocks, start=1):
        lines.append(
            f"{index}. {stock['name']}（{stock['code']}） 涨跌 "
            f"{stock.get('change_pct', 0):+.2f}% | 成交 {_yi(stock.get('turnover', 0))}亿 | "
            f"净流入 {_yi(stock.get('net_inflow', 0))}亿 | 综合分 {stock.get('score', 0):.2f}"
        )
        lines.append(stock.get("summary", ""))
        for item in (stock.get("news") or [])[:2]:
            title = item.get("title") or "相关新闻"
            url = item.get("url") or ""
            lines.append(f"- {title}: {url}")
        lines.append("")
    return "\n".join(lines)


def save_report(
    markdown: str,
    stocks: list[dict[str, Any]],
    base_dir: str | Path,
    run_at: datetime | None = None,
) -> Path:
    run_at = run_at or datetime.now()
    report_dir = Path(base_dir) / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = run_at.strftime("%Y-%m-%d")
    target = report_dir / f"{stamp}.md"
    target.write_text(markdown, encoding="utf-8")
    latest = report_dir / "latest.md"
    latest.write_text(markdown, encoding="utf-8")
    data_file = report_dir / f"{stamp}.json"
    data_file.write_text(
        json.dumps(
            {
                "run_at": run_at.isoformat(),
                "top_stocks": stocks,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return target
