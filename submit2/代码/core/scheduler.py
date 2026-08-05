from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError


class DailyScheduler:
    """在指定北京时间每日触发的调度器。"""

    def __init__(
        self,
        run_hour: int,
        run_minute: int,
        on_run: Callable[[], None],
        tz_name: str = "Asia/Shanghai",
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.run_hour = int(run_hour)
        self.run_minute = int(run_minute)
        self.on_run = on_run
        try:
            self.tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            self.tz = timezone(timedelta(hours=8), name="UTC+8")
        self.log = log or (lambda _: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def next_run_time(self) -> datetime:
        now = datetime.now(self.tz)
        target = now.replace(
            hour=self.run_hour,
            minute=self.run_minute,
            second=0,
            microsecond=0,
        )
        if target <= now:
            target += timedelta(days=1)
        return target

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="daily-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            target = self.next_run_time()
            delay = max(1, (target - datetime.now(self.tz)).total_seconds())
            if self._stop.wait(delay):
                break
            try:
                self.log(f"定时触发：{target:%Y-%m-%d %H:%M}（北京时间）")
                self.on_run()
            except Exception as exc:
                self.log(f"定时任务异常: {exc}")
