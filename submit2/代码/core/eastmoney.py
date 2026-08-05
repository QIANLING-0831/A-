from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError


try:
    BEIJING_TZ = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:
    BEIJING_TZ = timezone(timedelta(hours=8), name="UTC+8")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}
CLIST_HOSTS = [
    "https://push2.eastmoney.com",
    "https://push2delay.eastmoney.com",
    "https://82.push2.eastmoney.com",
]


def _num(value: Any) -> float:
    if value is None or value == "-":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _get_json(
    url: str,
    params: dict[str, Any],
    referer: str,
    timeout: float = 15,
) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    headers = dict(HEADERS)
    headers["Referer"] = referer
    request = urllib.request.Request(
        f"{url}?{query}",
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read().decode("utf-8", "replace")
    if text.lstrip().startswith(("{", "[")):
        return json.loads(text)
    start = text.find("(")
    end = text.rfind(")")
    if start < 0 or end < start:
        raise ValueError("接口返回格式异常")
    return json.loads(text[start + 1 : end])


def fetch_board_constituents(
    board_code: str = "BK0809",
    timeout: float = 15,
) -> list[dict[str, Any]]:
    """获取东方财富概念板块成分股及当日行情、资金流。"""
    last_error: Exception | None = None
    payload: dict[str, Any] = {}
    stocks: list[dict[str, Any]] = []
    seen: set[str] = set()
    page = 1
    total = 0
    while True:
        params = {
            "cb": "jQueryCodex",
            "pn": page,
            "pz": 100,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": f"b:{board_code}",
            "fields": "f12,f14,f2,f3,f6,f62,f100,f184",
        }
        payload = {}
        for host in CLIST_HOSTS:
            try:
                payload = _get_json(
                    f"{host}/api/qt/clist/get",
                    params,
                    referer="https://quote.eastmoney.com/",
                    timeout=timeout,
                )
                break
            except Exception as exc:
                last_error = exc
                continue
        if not payload:
            raise RuntimeError(f"东方财富行情接口全部失败: {last_error}")
        data = payload.get("data") or {}
        total = int(data.get("total") or 0)
        rows = data.get("diff") or []
        for row in rows:
            code = str(row.get("f12") or "")
            if code in seen:
                continue
            seen.add(code)
            stocks.append(
                {
                    "code": code,
                    "name": str(row.get("f14") or ""),
                    "price": _num(row.get("f2")),
                    "change_pct": _num(row.get("f3")),
                    "turnover": _num(row.get("f6")),
                    "net_inflow": _num(row.get("f62")),
                    "industry": str(row.get("f100") or ""),
                    "main_inflow_pct": _num(row.get("f184")),
                    "news_count": 0,
                    "news": [],
                }
            )
        if not rows or len(stocks) >= total or page >= 10:
            break
        page += 1
    return stocks


def search_news(
    keyword: str,
    page_size: int = 30,
    sort: str = "time",
    timeout: float = 12,
) -> list[dict[str, Any]]:
    """按关键词搜索东方财富资讯，返回按时间排序的新闻列表。"""
    param = {
        "uid": "",
        "keyword": keyword,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": sort,
                "pageIndex": 1,
                "pageSize": page_size,
                "preTag": "<em>",
                "postTag": "</em>",
            }
        },
    }
    payload = _get_json(
        "https://search-api-web.eastmoney.com/search/jsonp",
        {"cb": "jQueryCodex", "param": json.dumps(param, ensure_ascii=False)},
        referer="https://so.eastmoney.com/",
        timeout=timeout,
    )
    items = (payload.get("result") or {}).get("cmsArticleWebOld") or []
    news: list[dict[str, Any]] = []
    for item in items:
        title = re.sub(r"</?em>", "", str(item.get("title") or ""))
        content = re.sub(r"</?em>", "", str(item.get("content") or ""))
        news.append(
            {
                "title": title,
                "url": str(item.get("url") or ""),
                "date": str(item.get("date") or ""),
                "media": str(item.get("mediaName") or ""),
                "content": content[:80],
            }
        )
    news.sort(key=lambda item: item["date"], reverse=True)
    return news


def _parse_news_date(value: str) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:19], fmt).date()
        except ValueError:
            continue
    return None


def _fetch_one(
    keyword: str,
    page_size: int,
    news_days: int,
    today: date,
    limit: int,
) -> dict[str, Any]:
    try:
        items = search_news(keyword, page_size=page_size)
    except Exception:
        return {"count": 0, "news": []}
    start = today - timedelta(days=max(0, news_days - 1))
    count = 0
    recent: list[dict[str, Any]] = []
    for item in items:
        item_date = _parse_news_date(item["date"])
        if item_date is None or item_date >= start:
            count += 1
            recent.append(item)
    return {"count": count, "news": recent[:limit]}


def fetch_news_counts(
    stocks: list[dict[str, Any]],
    page_size: int = 30,
    news_days: int = 1,
    news_link_count: int = 3,
    max_workers: int = 8,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """并发抓取每只股票的新闻提及数与最新新闻链接。"""
    today = datetime.now(BEIJING_TZ).date()
    results: dict[str, dict[str, Any]] = {}
    total = len(stocks)

    def task(index: int, stock: dict[str, Any]) -> tuple[int, str, dict[str, Any]]:
        name = stock["name"]
        if progress:
            progress(index + 1, total, name)
        return index, name, _fetch_one(name, page_size, news_days, today, news_link_count)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(task, index, stock) for index, stock in enumerate(stocks)]
        for future in as_completed(futures):
            index, name, result = future.result()
            results[name] = result
    return results


def attach_news(
    stocks: list[dict[str, Any]],
    news_map: dict[str, dict[str, Any]],
) -> None:
    for stock in stocks:
        data = news_map.get(stock["name"], {"count": 0, "news": []})
        stock["news_count"] = data["count"]
        stock["news"] = data["news"]
