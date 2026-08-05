from __future__ import annotations

from typing import Any


METRICS = {
    "turnover": "成交额",
    "change": "涨跌幅",
    "net_inflow": "资金净流入",
    "news": "新闻提及",
}
METRIC_VALUE_KEYS = {
    "turnover": "turnover",
    "change": "change_pct",
    "net_inflow": "net_inflow",
    "news": "news_count",
}


def validate_weights(weights: dict[str, float]) -> float:
    missing = set(METRICS) - set(weights)
    if missing:
        raise ValueError(f"缺少评分权重: {', '.join(sorted(missing))}")
    total = 0.0
    for key, value in weights.items():
        total += float(value)
        if float(value) < 0:
            raise ValueError("评分权重不能为负数")
    if total <= 0:
        raise ValueError("评分权重之和必须大于 0")
    return total


def _percentile_ranks(values: list[float]) -> list[float]:
    total = len(values)
    if total == 0:
        return []
    return [
        (
            sum(1 for other in values if other < value)
            + 0.5 * sum(1 for other in values if other == value)
        )
        / total
        * 100.0
        for value in values
    ]


def compute_scores(
    stocks: list[dict[str, Any]],
    weights: dict[str, float],
) -> list[dict[str, Any]]:
    """按板块内百分位计算综合热度分，数值越大越热。"""
    validate_weights(weights)
    total_weight = sum(float(weights[key]) for key in METRICS)
    ranked = [dict(stock) for stock in stocks]
    for metric in METRICS:
        value_key = METRIC_VALUE_KEYS[metric]
        values = [_num(stock.get(value_key)) for stock in ranked]
        ranks = _percentile_ranks(values)
        for stock, rank in zip(ranked, ranks):
            stock[f"{metric}_rank"] = round(rank, 2)
    for stock in ranked:
        score = sum(
            float(weights[metric]) * float(stock[f"{metric}_rank"])
            for metric in METRICS
        ) / total_weight
        stock["score"] = round(score, 2)
        stock["score_parts"] = {
            metric: {
                "weight": float(weights[metric]),
                "value": _num(stock.get(METRIC_VALUE_KEYS[metric])),
                "rank": float(stock[f"{metric}_rank"]),
            }
            for metric in METRICS
        }
    ranked.sort(key=lambda stock: (-stock["score"], -stock["turnover"]))
    return ranked


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _yi(value: float) -> str:
    amount = value / 1e8
    return f"{amount:.2f}亿"


def make_summary(
    stock: dict[str, Any],
    rank: int,
    board_name: str = "AI智能体",
    max_len: int = 49,
) -> str:
    """生成不超过 max_len 字的中文摘要，先长后短逐级裁剪。"""
    name = stock.get("name", "")
    change = f"{_num(stock.get('change_pct')):+.2f}%"
    turnover = _yi(_num(stock.get("turnover")))
    inflow = _yi(_num(stock.get("net_inflow")))
    news = int(_num(stock.get("news_count")))
    candidates = [
        f"{name}今日成交{turnover}，{change}，主力净流入{inflow}，"
        f"新闻{news}篇，{board_name}概念热度第{rank}名。",
        f"{name}成交{turnover}，{change}，净流入{inflow}，"
        f"新闻{news}篇，{board_name}热度第{rank}名。",
        f"{name}成交{turnover}，{change}，净流入{inflow}，"
        f"{board_name}热度第{rank}名。",
        f"{name}，{change}，净流入{inflow}，热度第{rank}名。",
    ]
    for candidate in candidates:
        if len(candidate) <= max_len:
            return candidate
    return candidates[-1][:max_len]
