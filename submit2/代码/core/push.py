from __future__ import annotations

import html
import json
import smtplib
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AIAgentHeatBot/1.0",
    "Content-Type": "application/json; charset=utf-8",
}


@dataclass
class PushOutcome:
    channel: str
    ok: bool
    message: str


def _post_json(url: str, payload: dict[str, Any], timeout: float = 20) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False)
    request = urllib.request.Request(url, data=body.encode("utf-8"), headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read().decode("utf-8", "replace")
    return json.loads(text)


def push_wecom(webhook_url: str, markdown: str) -> tuple[bool, str]:
    if webhook_url.startswith("key="):
        webhook_url = (
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?" + webhook_url
        )
    payload = {"msgtype": "markdown", "markdown": {"content": markdown[:4000]}}
    result = _post_json(webhook_url, payload)
    if result.get("errcode") == 0:
        return True, "企业微信推送成功"
    return False, f"企业微信推送失败: {result}"


def push_feishu(webhook_url: str, markdown: str, title: str) -> tuple[bool, str]:
    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": title[:200]},
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": markdown[:30000]}}
            ],
        },
    }
    result = _post_json(webhook_url, card)
    if result.get("code") in (0, None):
        return True, "飞书推送成功"
    return False, f"飞书推送失败: {result}"


def push_dingtalk(webhook_url: str, markdown: str, title: str) -> tuple[bool, str]:
    if webhook_url.startswith("access_token="):
        webhook_url = (
            "https://oapi.dingtalk.com/robot/send?" + webhook_url
        )
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title[:200], "text": markdown[:20000]},
    }
    result = _post_json(webhook_url, payload)
    if result.get("errcode") == 0:
        return True, "钉钉推送成功"
    return False, f"钉钉推送失败: {result}"


def push_telegram(bot_token: str, chat_id: str, text: str) -> tuple[bool, str]:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text[:4000],
            "disable_web_page_preview": "false",
        }
    ).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8", "replace"))
    if result.get("ok"):
        return True, "Telegram 推送成功"
    return False, f"Telegram 推送失败: {result}"


def _build_email_html(markdown: str) -> str:
    safe = html.escape(markdown)
    safe = safe.replace("\n\n", "<br/><br/>").replace("\n", "<br/>")
    return (
        "<html><body style='font-family:Microsoft YaHei, sans-serif;font-size:14px'>"
        f"{safe}</body></html>"
    )


def push_email(
    email_cfg: dict[str, Any],
    markdown: str,
    title: str,
) -> tuple[bool, str]:
    host = email_cfg.get("smtp_host") or ""
    port = int(email_cfg.get("smtp_port") or 465)
    username = email_cfg.get("username") or ""
    password = email_cfg.get("password") or ""
    from_addr = email_cfg.get("from_addr") or username
    to_addrs = email_cfg.get("to_addrs") or []
    if isinstance(to_addrs, str):
        to_addrs = [item.strip() for item in to_addrs.split(",") if item.strip()]
    if not (host and username and password and from_addr and to_addrs):
        return False, "邮件配置不完整"
    message = EmailMessage()
    message["Subject"] = title[:200]
    message["From"] = from_addr
    message["To"] = ", ".join(to_addrs)
    message.set_content(markdown[:40000])
    message.add_alternative(_build_email_html(markdown[:40000]), subtype="html")
    if email_cfg.get("use_ssl", True):
        with smtplib.SMTP_SSL(host, port, timeout=20) as server:
            server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.login(username, password)
            server.send_message(message)
    return True, f"邮件推送成功（{len(to_addrs)} 个收件人）"


def push_all(
    push_cfg: dict[str, Any],
    markdown: str,
    plain_text: str,
    title: str = "AI智能体 概念热度榜",
) -> list[PushOutcome]:
    outcomes: list[PushOutcome] = []

    wecom = push_cfg.get("wecom") or {}
    if wecom.get("enabled") and wecom.get("webhook_url"):
        try:
            ok, message = push_wecom(wecom["webhook_url"], markdown)
        except Exception as exc:
            ok, message = False, f"企业微信推送异常: {exc}"
        outcomes.append(PushOutcome("企业微信", ok, message))

    feishu = push_cfg.get("feishu") or {}
    if feishu.get("enabled") and feishu.get("webhook_url"):
        try:
            ok, message = push_feishu(feishu["webhook_url"], markdown, title)
        except Exception as exc:
            ok, message = False, f"飞书推送异常: {exc}"
        outcomes.append(PushOutcome("飞书", ok, message))

    dingtalk = push_cfg.get("dingtalk") or {}
    if dingtalk.get("enabled") and dingtalk.get("webhook_url"):
        try:
            ok, message = push_dingtalk(dingtalk["webhook_url"], markdown, title)
        except Exception as exc:
            ok, message = False, f"钉钉推送异常: {exc}"
        outcomes.append(PushOutcome("钉钉", ok, message))

    telegram = push_cfg.get("telegram") or {}
    if (
        telegram.get("enabled")
        and telegram.get("bot_token")
        and telegram.get("chat_id")
    ):
        try:
            ok, message = push_telegram(
                telegram["bot_token"], telegram["chat_id"], plain_text
            )
        except Exception as exc:
            ok, message = False, f"Telegram 推送异常: {exc}"
        outcomes.append(PushOutcome("Telegram", ok, message))

    email = push_cfg.get("email") or {}
    if email.get("enabled"):
        try:
            ok, message = push_email(email, markdown, title)
        except Exception as exc:
            ok, message = False, f"邮件推送异常: {exc}"
        outcomes.append(PushOutcome("邮件", ok, message))

    return outcomes


def send_test_message(push_cfg: dict[str, Any]) -> list[PushOutcome]:
    return push_all(
        push_cfg,
        markdown="# 测试消息\n\nAI智能体热度榜推送配置正常。",
        plain_text="测试消息：AI智能体热度榜推送配置正常。",
        title="AI智能体热度榜 - 测试",
    )
