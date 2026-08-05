from __future__ import annotations

import os
import queue
import sys
import threading
import webbrowser
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
import tkinter as tk

from core import eastmoney
from core.config import load_config, save_config
from core.push import send_test_message
from core.scheduler import DailyScheduler
from core.workflow import run_workflow


BASE_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
FONT = ("Microsoft YaHei UI", 10)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 13, "bold")


class HeatApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AIAgent 智能体概念热度榜")
        self.geometry("1180x780")
        self.minsize(980, 640)
        self.config_data = load_config(BASE_DIR)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.scheduler: DailyScheduler | None = None
        self.run_thread: threading.Thread | None = None
        self.top_stocks: list[dict] = []
        self.news_urls: list[str] = []
        self.status_text = tk.StringVar(value="就绪")
        self.next_run_text = tk.StringVar(value="定时：未启动")
        self._build_ui()
        self._poll_queue()
        self._update_status()
        self.after(300, self._maybe_run_on_start)

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        toolbar = ttk.Frame(self, padding=(12, 10, 12, 6))
        toolbar.pack(fill="x")
        ttk.Label(
            toolbar,
            text="AIAgent 智能体概念热度榜",
            font=FONT_TITLE,
        ).pack(side="left")
        board = self.config_data["board"]
        self.board_label = ttk.Label(
            toolbar,
            text=f"{board['name']}（{board['code']}）",
            font=FONT_BOLD,
        )
        self.board_label.pack(side="left", padx=(14, 0))
        self.run_btn = ttk.Button(toolbar, text="立即运行", command=self.start_run)
        self.run_btn.pack(side="right", padx=(6, 0))
        self.sched_btn = ttk.Button(
            toolbar, text="启动定时", command=self.toggle_scheduler
        )
        self.sched_btn.pack(side="right", padx=(6, 0))
        ttk.Button(
            toolbar, text="推送设置", command=self.open_settings
        ).pack(side="right", padx=(6, 0))
        ttk.Button(
            toolbar, text="打开报告目录", command=self.open_report_dir
        ).pack(side="right", padx=(6, 0))

        main = ttk.PanedWindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=12, pady=(4, 4))

        table_frame = ttk.Frame(main)
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        columns = (
            "rank",
            "code",
            "name",
            "price",
            "change",
            "turnover",
            "net",
            "news",
            "score",
        )
        self.table = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        headings = {
            "rank": "排名",
            "code": "代码",
            "name": "名称",
            "price": "最新价",
            "change": "涨跌幅",
            "turnover": "成交额(亿)",
            "net": "净流入(亿)",
            "news": "新闻",
            "score": "综合分",
        }
        widths = {
            "rank": 50,
            "code": 70,
            "name": 110,
            "price": 75,
            "change": 80,
            "turnover": 90,
            "net": 90,
            "news": 55,
            "score": 75,
        }
        for column in columns:
            self.table.heading(column, text=headings[column])
            anchor = "center" if column in {"rank", "code", "news", "score"} else "e"
            self.table.column(column, width=widths[column], anchor=anchor)
        table_scroll_y = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.table.yview
        )
        table_scroll_x = ttk.Scrollbar(
            table_frame, orient="horizontal", command=self.table.xview
        )
        self.table.configure(
            yscrollcommand=table_scroll_y.set,
            xscrollcommand=table_scroll_x.set,
        )
        self.table.grid(row=0, column=0, sticky="nsew")
        table_scroll_y.grid(row=0, column=1, sticky="ns")
        table_scroll_x.grid(row=1, column=0, sticky="ew")

        nav = ttk.Frame(table_frame)
        nav.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        nav.columnconfigure(2, weight=1)
        ttk.Button(
            nav, text="◀", width=3, command=lambda: self._shift_table(-1)
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            nav, text="▶", width=3, command=lambda: self._shift_table(1)
        ).grid(row=0, column=1, sticky="w", padx=(4, 0))

        self.table.bind("<<TreeviewSelect>>", self._show_detail)
        self.table.bind("<Left>", lambda _event: self._shift_table(-1))
        self.table.bind("<Right>", lambda _event: self._shift_table(1))
        self.table.bind(
            "<Shift-MouseWheel>",
            lambda event: self._shift_table(-1 if event.delta > 0 else 1),
        )
        main.add(table_frame, weight=3)

        detail_frame = ttk.Frame(main, padding=(10, 2, 0, 0))
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(0, weight=3)
        detail_frame.rowconfigure(1, weight=2)
        self.detail_text = tk.Text(
            detail_frame,
            height=14,
            wrap="word",
            font=FONT,
            state="disabled",
        )
        self.detail_text.tag_configure("title", font=FONT_TITLE)
        self.detail_text.tag_configure("bold", font=FONT_BOLD)
        self.detail_text.grid(row=0, column=0, sticky="nsew")
        news_label = ttk.Label(detail_frame, text="关键新闻", font=FONT_BOLD)
        news_label.grid(row=1, column=0, sticky="sw", pady=(8, 2))
        self.news_list = tk.Listbox(detail_frame, font=FONT, activestyle="dotbox")
        self.news_list.grid(row=2, column=0, sticky="nsew")
        news_scroll = ttk.Scrollbar(
            detail_frame, orient="vertical", command=self.news_list.yview
        )
        self.news_list.configure(yscrollcommand=news_scroll.set)
        news_scroll.grid(row=2, column=1, sticky="ns")
        open_btn = ttk.Button(
            detail_frame, text="在浏览器打开选中新闻", command=self.open_news
        )
        open_btn.grid(row=3, column=0, sticky="w", pady=(6, 0))
        main.add(detail_frame, weight=2)

        log_frame = ttk.LabelFrame(self, text="运行日志", padding=(8, 4))
        log_frame.pack(fill="both", expand=False, padx=12, pady=(0, 6))
        self.log_text = tk.Text(log_frame, height=7, wrap="word", font=FONT)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self.log_text.configure(state="disabled")

        status = ttk.Frame(self, padding=(12, 2, 12, 8))
        status.pack(fill="x")
        ttk.Label(status, textvariable=self.status_text).pack(side="left")
        ttk.Label(status, textvariable=self.next_run_text).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{datetime.now():%H:%M:%S}  {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "progress":
                    self.status_text.set(str(payload))
                elif kind == "done":
                    self._on_run_done(payload)
                elif kind == "error":
                    self.run_btn.configure(state="normal")
                    self.status_text.set("运行失败")
                    self._append_log(f"运行失败: {payload}")
                    messagebox.showerror("运行失败", str(payload), parent=self)
                elif kind == "push_test_done":
                    self._show_push_test_result(payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _maybe_run_on_start(self) -> None:
        if self.config_data["schedule"].get("run_on_start"):
            self._append_log("配置了启动时立即运行，开始执行。")
            self.start_run()

    def start_run(self) -> None:
        if self.run_thread and self.run_thread.is_alive():
            return
        self.run_btn.configure(state="disabled")
        self.status_text.set("正在运行...")
        self._append_log("任务开始。")

        def worker() -> None:
            try:
                result = run_workflow(
                    self.config_data,
                    log=lambda message: self.events.put(("log", message)),
                    progress=lambda i, total, name: self.events.put(
                        ("progress", f"新闻抓取 {i}/{total}: {name}")
                    ),
                    base_dir=str(BASE_DIR),
                )
                self.events.put(("done", result))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        self.run_thread = threading.Thread(target=worker, daemon=True)
        self.run_thread.start()

    def _on_run_done(self, result: dict) -> None:
        self.run_btn.configure(state="normal")
        self.top_stocks = result["top_stocks"]
        self.table.delete(*self.table.get_children())
        for stock in self.top_stocks:
            self.table.insert(
                "",
                "end",
                values=(
                    stock.get("rank", ""),
                    stock.get("code", ""),
                    stock.get("name", ""),
                    f"{stock.get('price', 0):.2f}",
                    f"{stock.get('change_pct', 0):+.2f}%",
                    f"{stock.get('turnover', 0) / 1e8:.2f}",
                    f"{stock.get('net_inflow', 0) / 1e8:+.2f}",
                    int(stock.get("news_count", 0)),
                    f"{stock.get('score', 0):.2f}",
                ),
            )
        if self.top_stocks:
            first = self.table.get_children()[0]
            self.table.selection_set(first)
            self.table.focus(first)
        push_ok = sum(1 for o in result["push_outcomes"] if o.ok)
        push_total = len(result["push_outcomes"])
        self.status_text.set(
            f"运行完成：{result['run_at']:%Y-%m-%d %H:%M}，"
            f"{result['total_count']} 只成分股，推送 {push_ok}/{push_total}"
        )
        self._append_log(f"运行完成，报告：{result['report_path']}")
        self._update_status()

    def _show_detail(self, _event=None) -> None:
        selection = self.table.selection()
        if not selection or not self.top_stocks:
            return
        row = self.table.index(selection[0])
        stock = self.top_stocks[row]
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        parts = stock.get("score_parts", {})
        self.detail_text.insert(
            "end", f"{stock['name']}（{stock['code']}）\n", "title"
        )
        self.detail_text.insert(
            "end",
            f"行业：{stock.get('industry') or '-'}    综合分：{stock.get('score', 0):.2f}\n\n",
            "bold",
        )
        self.detail_text.insert("end", f"摘要：{stock.get('summary', '')}\n\n")
        self.detail_text.insert(
            "end",
            (
                f"最新价 {stock.get('price', 0):.2f}，"
                f"涨跌幅 {stock.get('change_pct', 0):+.2f}%，"
                f"成交额 {stock.get('turnover', 0) / 1e8:.2f} 亿，"
                f"主力净流入 {stock.get('net_inflow', 0) / 1e8:+.2f} 亿，"
                f"新闻提及 {int(stock.get('news_count', 0))} 条\n\n"
            ),
        )
        for label, key in (
            ("成交额", "turnover"),
            ("涨跌幅", "change"),
            ("资金净流入", "net_inflow"),
            ("新闻提及", "news"),
        ):
            part = parts.get(key) or {}
            self.detail_text.insert(
                "end",
                f"{label}：权重 {part.get('weight', 0):g}%，"
                f"板块内分 {part.get('rank', 0):.1f}\n",
            )
        self.detail_text.insert(
            "end", "\n选中下方新闻条目后点击按钮在浏览器打开。"
        )
        self.detail_text.configure(state="disabled")
        self.news_urls = []
        self.news_list.delete(0, "end")
        for item in stock.get("news") or []:
            self.news_urls.append(item.get("url", ""))
            self.news_list.insert(
                "end",
                f"{item.get('title', '')}（{item.get('date', '')}）",
            )
        if self.news_urls:
            self.news_list.selection_set(0)

    def open_news(self) -> None:
        selection = self.news_list.curselection()
        if not selection:
            return
        url = self.news_urls[selection[0]]
        if url:
            webbrowser.open(url)

    def _shift_table(self, direction: int) -> None:
        first, last = self.table.xview()
        span = last - first
        if span <= 0:
            return
        step = span * 0.4
        if direction < 0:
            new_first = max(first - step, 0.0)
        else:
            new_first = min(first + step, max(0.0, 1.0 - span))
        self.table.xview_moveto(new_first)

    def toggle_scheduler(self) -> None:
        if self.scheduler and self.scheduler._thread and self.scheduler._thread.is_alive():
            self.scheduler.stop()
            self.scheduler = None
            self.sched_btn.configure(text="启动定时")
            self._append_log("定时调度已停止。")
        else:
            schedule = self.config_data["schedule"]
            self.scheduler = DailyScheduler(
                run_hour=int(schedule.get("run_hour", 11)),
                run_minute=int(schedule.get("run_minute", 0)),
                on_run=lambda: self.after(0, self.start_run),
                log=lambda message: self.events.put(("log", message)),
            )
            self.scheduler.start()
            self.sched_btn.configure(text="停止定时")
            self._append_log(
                f"定时调度已启动，下次运行：{self.scheduler.next_run_time():%Y-%m-%d %H:%M}（北京时间）。"
            )
        self._update_status()

    def _update_status(self) -> None:
        if self.scheduler and self.scheduler._thread and self.scheduler._thread.is_alive():
            self.next_run_text.set(
                f"下次运行：{self.scheduler.next_run_time():%Y-%m-%d %H:%M}（北京时间）"
            )
        else:
            self.next_run_text.set("定时：未启动")
        self.after(1000, self._update_status)

    def open_settings(self) -> None:
        SettingsDialog(self)

    def open_report_dir(self) -> None:
        report_dir = BASE_DIR / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(report_dir))

    def _on_close(self) -> None:
        if self.scheduler:
            self.scheduler.stop()
        self.destroy()

    def _show_push_test_result(self, payload: object) -> None:
        outcomes = payload
        if not isinstance(outcomes, list):
            messagebox.showerror("测试推送", str(outcomes), parent=self)
            return
        lines = [f"{o.channel}：{'成功' if o.ok else '失败'} {o.message}" for o in outcomes]
        messagebox.showinfo("测试推送", "\n".join(lines) or "未启用任何推送渠道", parent=self)


class SettingsDialog(tk.Toplevel):
    def __init__(self, master: HeatApp) -> None:
        super().__init__(master)
        self.master_app = master
        self.config = deepcopy(master.config_data)
        self.title("设置")
        self.geometry("760x640")
        self.transient(master)
        self.grab_set()
        self.vars: dict[str, tk.Variable] = {}
        self._build()
        self._load_values()

    def _build(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        basic = ttk.Frame(notebook, padding=12)
        notebook.add(basic, text="基础设置")
        self._add_label(basic, "基础设置", 0, 0, font=FONT_TITLE)
        rows = [
            ("board_code", "板块代码"),
            ("board_name", "板块名称"),
            ("top_n", "榜单数量 Top N"),
            ("news_page_size", "每只股票新闻抓取条数"),
            ("news_days", "新闻提及统计天数"),
            ("news_link_count", "每只股票展示新闻链接数"),
            ("run_hour", "每日运行小时（北京时间）"),
            ("run_minute", "每日运行分钟"),
        ]
        for index, (key, label) in enumerate(rows, start=1):
            self._add_label(basic, label, index, 0)
            var = tk.StringVar()
            self.vars[key] = var
            entry = ttk.Entry(basic, textvariable=var, width=30)
            entry.grid(row=index, column=1, sticky="w", pady=3)
        self.vars["run_on_start"] = tk.BooleanVar()
        ttk.Checkbutton(
            basic,
            text="程序启动后立即运行一次",
            variable=self.vars["run_on_start"],
        ).grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w", pady=6)

        weight = ttk.Frame(notebook, padding=12)
        notebook.add(weight, text="评分权重")
        self._add_label(weight, "热度综合分权重（按板块内百分位计算）", 0, 0, font=FONT_TITLE)
        weight_rows = [
            ("turnover", "成交额 40%"),
            ("change", "涨跌幅 30%"),
            ("net_inflow", "资金净流入 20%"),
            ("news", "新闻提及 10%"),
        ]
        for index, (key, label) in enumerate(weight_rows, start=1):
            self._add_label(weight, label, index, 0)
            var = tk.StringVar()
            self.vars[f"weight_{key}"] = var
            ttk.Entry(weight, textvariable=var, width=12).grid(
                row=index, column=1, sticky="w", pady=3
            )

        push_tab = ttk.Frame(notebook, padding=12)
        notebook.add(push_tab, text="推送渠道")
        self._build_push_tab(push_tab)

        buttons = ttk.Frame(self, padding=10)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="保存", command=self._save).pack(side="right", padx=4)
        ttk.Button(buttons, text="取消", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(
            buttons, text="测试已启用渠道", command=self._test_push
        ).pack(side="left")

    def _build_push_tab(self, parent: ttk.Frame) -> None:
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        row = 0

        def channel_header(name: str) -> None:
            nonlocal row
            self._add_label(inner, name, row, 0, font=FONT_BOLD)
            row += 1

        def field(key: str, label: str, show: str | None = None) -> None:
            nonlocal row
            self._add_label(inner, label, row, 0)
            var = tk.StringVar()
            self.vars[key] = var
            ttk.Entry(inner, textvariable=var, width=52, show=show or "").grid(
                row=row, column=1, sticky="w", pady=2
            )
            row += 1

        def check(key: str, label: str) -> None:
            nonlocal row
            var = tk.BooleanVar()
            self.vars[key] = var
            ttk.Checkbutton(inner, text=label, variable=var).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=2
            )
            row += 1

        channel_header("企业微信机器人")
        check("push_wecom_enabled", "启用企业微信推送")
        field("push_wecom_url", "Webhook 地址")

        channel_header("飞书机器人")
        check("push_feishu_enabled", "启用飞书推送")
        field("push_feishu_url", "Webhook 地址")

        channel_header("钉钉机器人")
        check("push_dingtalk_enabled", "启用钉钉推送")
        field("push_dingtalk_url", "Webhook 地址")

        channel_header("Telegram")
        check("push_telegram_enabled", "启用 Telegram 推送")
        field("push_telegram_token", "Bot Token")
        field("push_telegram_chat", "Chat ID")

        channel_header("邮件")
        check("push_email_enabled", "启用邮件推送")
        field("push_email_host", "SMTP 服务器")
        field("push_email_port", "SMTP 端口")
        check("push_email_ssl", "使用 SSL 连接（否则 STARTTLS）")
        field("push_email_user", "用户名")
        field("push_email_password", "密码 / 授权码", show="*")
        field("push_email_from", "发件地址")
        field("push_email_to", "收件地址（多个用逗号分隔）")

    def _add_label(
        self,
        parent: ttk.Frame,
        text: str,
        row: int,
        column: int,
        font=("Microsoft YaHei UI", 10),
    ) -> None:
        ttk.Label(parent, text=text, font=font).grid(
            row=row, column=column, sticky="w", padx=(0, 8), pady=3
        )

    def _load_values(self) -> None:
        board = self.config["board"]
        scoring = self.config["scoring"]
        schedule = self.config["schedule"]
        push = self.config["push"]
        for key, value in {
            "board_code": board["code"],
            "board_name": board["name"],
            "top_n": scoring["top_n"],
            "news_page_size": scoring["news_page_size"],
            "news_days": scoring["news_days"],
            "news_link_count": scoring["news_link_count"],
            "run_hour": schedule["run_hour"],
            "run_minute": schedule["run_minute"],
        }.items():
            self.vars[key].set(str(value))
        self.vars["run_on_start"].set(bool(schedule.get("run_on_start")))
        for key, value in scoring["weights"].items():
            self.vars[f"weight_{key}"].set(str(value))
        self.vars["push_wecom_enabled"].set(bool(push["wecom"]["enabled"]))
        self.vars["push_wecom_url"].set(push["wecom"]["webhook_url"])
        self.vars["push_feishu_enabled"].set(bool(push["feishu"]["enabled"]))
        self.vars["push_feishu_url"].set(push["feishu"]["webhook_url"])
        self.vars["push_dingtalk_enabled"].set(bool(push["dingtalk"]["enabled"]))
        self.vars["push_dingtalk_url"].set(push["dingtalk"]["webhook_url"])
        self.vars["push_telegram_enabled"].set(bool(push["telegram"]["enabled"]))
        self.vars["push_telegram_token"].set(push["telegram"]["bot_token"])
        self.vars["push_telegram_chat"].set(push["telegram"]["chat_id"])
        email = push["email"]
        self.vars["push_email_enabled"].set(bool(email["enabled"]))
        self.vars["push_email_host"].set(email["smtp_host"])
        self.vars["push_email_port"].set(str(email["smtp_port"]))
        self.vars["push_email_ssl"].set(bool(email["use_ssl"]))
        self.vars["push_email_user"].set(email["username"])
        self.vars["push_email_password"].set(email["password"])
        self.vars["push_email_from"].set(email["from_addr"])
        self.vars["push_email_to"].set(", ".join(email["to_addrs"]))

    def _collect(self) -> dict:
        config = self.config
        board = config["board"]
        scoring = config["scoring"]
        schedule = config["schedule"]
        push = config["push"]
        board["code"] = self.vars["board_code"].get().strip() or "BK0809"
        board["name"] = self.vars["board_name"].get().strip() or "AI智能体"
        scoring["top_n"] = int(self.vars["top_n"].get() or 10)
        scoring["news_page_size"] = int(self.vars["news_page_size"].get() or 30)
        scoring["news_days"] = int(self.vars["news_days"].get() or 1)
        scoring["news_link_count"] = int(self.vars["news_link_count"].get() or 3)
        schedule["run_hour"] = int(self.vars["run_hour"].get() or 11)
        schedule["run_minute"] = int(self.vars["run_minute"].get() or 0)
        schedule["run_on_start"] = bool(self.vars["run_on_start"].get())
        for key in ("turnover", "change", "net_inflow", "news"):
            scoring["weights"][key] = float(self.vars[f"weight_{key}"].get() or 0)
        push["wecom"]["enabled"] = bool(self.vars["push_wecom_enabled"].get())
        push["wecom"]["webhook_url"] = self.vars["push_wecom_url"].get().strip()
        push["feishu"]["enabled"] = bool(self.vars["push_feishu_enabled"].get())
        push["feishu"]["webhook_url"] = self.vars["push_feishu_url"].get().strip()
        push["dingtalk"]["enabled"] = bool(self.vars["push_dingtalk_enabled"].get())
        push["dingtalk"]["webhook_url"] = self.vars["push_dingtalk_url"].get().strip()
        push["telegram"]["enabled"] = bool(self.vars["push_telegram_enabled"].get())
        push["telegram"]["bot_token"] = self.vars["push_telegram_token"].get().strip()
        push["telegram"]["chat_id"] = self.vars["push_telegram_chat"].get().strip()
        email = push["email"]
        email["enabled"] = bool(self.vars["push_email_enabled"].get())
        email["smtp_host"] = self.vars["push_email_host"].get().strip()
        email["smtp_port"] = int(self.vars["push_email_port"].get() or 465)
        email["use_ssl"] = bool(self.vars["push_email_ssl"].get())
        email["username"] = self.vars["push_email_user"].get().strip()
        email["password"] = self.vars["push_email_password"].get().strip()
        email["from_addr"] = self.vars["push_email_from"].get().strip()
        email["to_addrs"] = [
            item.strip()
            for item in self.vars["push_email_to"].get().split(",")
            if item.strip()
        ]
        return config

    def _save(self) -> None:
        try:
            config = self._collect()
            save_config(config, BASE_DIR)
        except (ValueError, OSError) as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return
        self.master_app.config_data = config
        board = config["board"]
        self.master_app.board_label.configure(
            text=f"{board['name']}（{board['code']}）"
        )
        self.master_app._append_log("设置已保存。")
        self.destroy()

    def _test_push(self) -> None:
        try:
            config = self._collect()
        except ValueError as exc:
            messagebox.showerror("配置错误", str(exc), parent=self)
            return

        def worker() -> None:
            try:
                outcomes = send_test_message(config["push"])
                self.master_app.events.put(("push_test_done", outcomes))
            except Exception as exc:
                self.master_app.events.put(("push_test_done", str(exc)))

        threading.Thread(target=worker, daemon=True).start()


def main() -> None:
    app = HeatApp()
    app.mainloop()


if __name__ == "__main__":
    main()
