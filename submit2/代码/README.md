# test2：AIAgent 智能体概念热度榜自动化工作流

每天北京时间 11:00 自动抓取 A 股“AI智能体”概念板块成分股，按热度综合分排序取 Top10，为每只股票生成 49 字以内（<50 字）摘要和当日关键新闻链接，并把榜单同步推送到企业微信、飞书、钉钉、Telegram 或邮件。

## 文件结构

| 文件 | 说明 |
| --- | --- |
| `app.py` | 桌面窗口主程序（tkinter，双击 `run.bat` 或 `dist\test2.exe` 打开） |
| `core/eastmoney.py` | 东方财富概念板块、行情资金流、新闻搜索抓取 |
| `core/scoring.py` | 热度综合分计算与 49 字以内摘要生成 |
| `core/report.py` | Markdown/纯文本报告生成与保存 |
| `core/push.py` | 企业微信 / 飞书 / 钉钉 / Telegram / 邮件推送 |
| `core/scheduler.py` | 每日北京时间定时调度 |
| `core/workflow.py` | 工作流编排（抓取 → 评分 → 摘要 → 报告 → 推送） |
| `core/config.py` | 配置文件读写 |
| `config.example.json` | 配置模板，首次运行会生成 `config.json` |
| `run.bat` | 双击启动（优先 `dist\test2.exe`，否则用 `pythonw`） |
| `build_exe.bat` | 用 PyInstaller 打包成免 Python 环境的 `dist\test2.exe` |
| `tests/test_core.py` | 评分、摘要、报告单元测试 |

## 运行

```bash
# 双击 run.bat，或命令行执行：
py -3 app.py

# 单元测试
py -3 -m unittest discover -s tests

# 不打开窗口直接跑一次完整流程（可加入系统计划任务）
py -3 -m core.workflow_cli
```

`workflow_cli.py` 是纯命令行入口：`py -3 -m core.workflow_cli` 会读取 `config.json` 执行一次完整流程并打印结果。

## 热度综合分

在板块内对每项指标做百分位归一化（越高越热），再按权重加权：

```text
综合分 = 成交额 40% + 涨跌幅 30% + 资金净流入 20% + 新闻提及 10%
```

新闻提及数按“近 N 天（默认 1 天）东方财富资讯中提及股票名称的条数”统计。权重可在窗口“推送设置 → 评分权重”中调整。

## 推送配置

在窗口点击“推送设置”，填写对应渠道后点“测试已启用渠道”验证，再保存：

- 企业微信：机器人 Webhook 地址
- 飞书：自定义机器人 Webhook 地址
- 钉钉：自定义机器人 Webhook 地址（可选加签）
- Telegram：Bot Token + Chat ID
- 邮件：SMTP 服务器、端口、账号、授权码、发件/收件地址

配置保存到 `config.json`，不含敏感信息的模板见 `config.example.json`。邮件密码建议使用邮箱服务商生成的授权码。

## 定时任务

窗口内点击“启动定时”即可；默认每天 11:00（北京时间）运行，运行时间和“启动后立即运行一次”可在设置中修改。窗口关闭后定时停止，如需离开窗口仍运行，可用 Windows 任务计划程序调用：

```bat
py -3 "C:\Users\钱铃\Desktop\ai test\test2\core\workflow_cli.py"
```

## 打包 exe

```bash
py -3 -m pip install pyinstaller
test2\build_exe.bat
```

生成 `test2\dist\test2.exe`，双击即可打开窗口，无需安装 Python。

## 数据源说明

- 板块：东方财富概念板块 `BK0809`（AI智能体），可在设置中改为其他概念板块代码
- 行情：东方财富 `push2.eastmoney.com` 成分股接口（成交额、涨跌幅、主力净流入）
- 新闻：东方财富资讯搜索接口，标题、日期、原文链接均来自搜索结果

数据接口均为公开接口，行情数据以交易所及东方财富为准；本工具输出仅作自动化研究演示，不构成投资建议。
