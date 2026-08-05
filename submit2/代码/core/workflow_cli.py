from __future__ import annotations

import sys
from pathlib import Path

from core.config import load_config
from core.workflow import run_workflow


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    config = load_config(base_dir)
    result = run_workflow(config, log=print, base_dir=str(base_dir))
    print()
    print(result["markdown"])
    print(f"\n报告已保存：{result['report_path']}")
    for outcome in result["push_outcomes"]:
        print(f"[{outcome.channel}] {outcome.message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
