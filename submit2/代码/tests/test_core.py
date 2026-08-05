from __future__ import annotations

import unittest

from core import scoring
from core.config import DEFAULT_CONFIG, load_config
from core.report import build_markdown, build_plain_text


def make_stock(
    name: str,
    turnover: float,
    change_pct: float,
    net_inflow: float,
    news_count: int,
) -> dict:
    return {
        "code": "000001",
        "name": name,
        "price": 10.0,
        "change_pct": change_pct,
        "turnover": turnover,
        "net_inflow": net_inflow,
        "industry": "IT服务Ⅱ",
        "main_inflow_pct": 5.0,
        "news_count": news_count,
        "news": [],
    }


class ScoringTests(unittest.TestCase):
    def test_compute_scores_sorts_by_heat(self) -> None:
        hot = make_stock("热度股", 100e8, 9.9, 5e8, 8)
        cold = make_stock("冷门股", 0.5e8, -3.0, -1e8, 0)
        ranked = scoring.compute_scores([hot, cold], {"turnover": 40, "change": 30, "net_inflow": 20, "news": 10})
        self.assertEqual(ranked[0]["name"], "热度股")
        self.assertGreater(ranked[0]["score"], ranked[1]["score"])
        self.assertIn("score_parts", ranked[0])

    def test_news_metric_affects_rank(self) -> None:
        base = make_stock("基础股", 50e8, 2.0, 1e8, 0)
        newsy = make_stock("新闻股", 50e8, 2.0, 1e8, 20)
        ranked = scoring.compute_scores([base, newsy], {"turnover": 40, "change": 30, "net_inflow": 20, "news": 10})
        self.assertEqual(ranked[0]["name"], "新闻股")

    def test_summary_under_50_chars(self) -> None:
        stock = make_stock("中文在线", 2053546629.28, 20.01, 487296816.0, 12)
        for rank in range(1, 11):
            summary = scoring.make_summary(stock, rank)
            self.assertLessEqual(len(summary), 49)
            self.assertIn("中文在线", summary)

    def test_weights_must_sum_to_positive(self) -> None:
        with self.assertRaises(ValueError):
            scoring.validate_weights({"turnover": 0, "change": 0, "net_inflow": 0, "news": 0})


class ConfigTests(unittest.TestCase):
    def test_default_config_shape(self) -> None:
        config = load_config()
        self.assertEqual(config["board"]["code"], "BK0809")
        self.assertEqual(config["scoring"]["weights"]["turnover"], 40)
        self.assertIn("email", config["push"])

    def test_merge_keeps_defaults(self) -> None:
        merged = dict(DEFAULT_CONFIG)
        merged["board"]["code"] = "BK9999"
        merged["scoring"]["weights"]["turnover"] = 50
        self.assertEqual(merged["scoring"]["weights"]["news"], 10)


class ReportTests(unittest.TestCase):
    def test_report_contains_rank_and_link(self) -> None:
        stocks = [
            {
                **make_stock("中文在线", 20.5e8, 10.0, 2e8, 3),
                "rank": 1,
                "score": 95.0,
                "summary": scoring.make_summary(make_stock("中文在线", 20.5e8, 10.0, 2e8, 3), 1),
                "news": [{"title": "相关新闻", "url": "https://example.com/news", "date": "2026-07-31", "media": "东方财富"}],
            }
        ]
        markdown = build_markdown(stocks, "BK0809", "AI智能体", 151, {"turnover": 40, "change": 30, "net_inflow": 20, "news": 10})
        self.assertIn("中文在线", markdown)
        self.assertIn("https://example.com/news", markdown)
        self.assertIn("Top1", markdown)
        plain = build_plain_text(stocks, "AI智能体")
        self.assertIn("相关新闻: https://example.com/news", plain)


if __name__ == "__main__":
    unittest.main()
