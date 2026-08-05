from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "board": {
        "code": "BK0809",
        "name": "AI智能体",
    },
    "scoring": {
        "top_n": 10,
        "news_page_size": 50,
        "news_days": 1,
        "news_link_count": 3,
        "weights": {
            "turnover": 40,
            "change": 30,
            "net_inflow": 20,
            "news": 10,
        },
    },
    "schedule": {
        "run_hour": 11,
        "run_minute": 0,
        "run_on_start": False,
    },
    "push": {
        "wecom": {"enabled": False, "webhook_url": ""},
        "feishu": {"enabled": False, "webhook_url": ""},
        "dingtalk": {"enabled": False, "webhook_url": ""},
        "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
        "email": {
            "enabled": False,
            "smtp_host": "smtp.qq.com",
            "smtp_port": 465,
            "use_ssl": True,
            "username": "",
            "password": "",
            "from_addr": "",
            "to_addrs": [],
        },
    },
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def config_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent
    return root / "config.json"


def load_config(base_dir: str | Path | None = None) -> dict[str, Any]:
    path = config_path(base_dir)
    if not path.exists():
        return deepcopy(DEFAULT_CONFIG)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return deepcopy(DEFAULT_CONFIG)
    return _merge(DEFAULT_CONFIG, raw)


def save_config(config: dict[str, Any], base_dir: str | Path | None = None) -> Path:
    path = config_path(base_dir)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
