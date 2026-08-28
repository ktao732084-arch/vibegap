"""全局常量与用户配置加载。全项目唯一允许出现字面常量的模块(§7.6)。"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, fields, replace
from pathlib import Path

logger = logging.getLogger(__name__)

DAEMON_HOST = "127.0.0.1"
DAEMON_PORT = 8765
POPUP_DELAY_SEC = 18       # ARMED → SHOWING 的延迟(防闪弹)
SUMMARY_LINGER_SEC = 2     # 软关闭小结停留时长
SESSION_TTL_MIN = 30       # 孤儿会话清理阈值
ADAPTER_TIMEOUT_SEC = 1    # 钩子上报 HTTP 超时
PANEL_ORIGIN_PATTERN = r"https?://(?:localhost|127\.0\.0\.1)(?::[0-9]+)?"
TICK_INTERVAL_SEC = 1      # 调度器定时脉冲间隔
IDLE_EXIT_MIN = 10         # 隐藏且无 Agent 活动多久后退出(保持闲置零进程)
TOAST_TIMEOUT_SEC = 5      # toast 子进程超时(效果在锁外执行,慢不阻塞事件,见 runtime.py)
LOG_RETENTION_DAYS = 7
SEED_RANGE = 2**31         # 洗牌种子取值上界(同一常量保证 seeded_order 的确定性)

# 本机服务身份。懒启动 helper 必须校验身份,不能把占用 8765 的其他程序当成 VibeGap。
SERVICE_ID = "vibegap"
SERVICE_PROTOCOL_VERSION = 1

MODE_SEQUENTIAL = "sequential"
MODE_SHUFFLED = "shuffled"
VALID_MODES = (MODE_SEQUENTIAL, MODE_SHUFFLED)

RESULT_PASS = "pass"
RESULT_FAIL = "fail"
RESULT_SKIP = "skip"
VALID_RESULTS = (RESULT_PASS, RESULT_FAIL, RESULT_SKIP)

# 新闻轮播(AIHOT,公开只读 API,要求可识别的非浏览器 UA;/api/public 2026 年底迁移 /api/v1)
NEWS_API_URL = "https://aihot.virxact.com/api/public/items?mode=selected&take=30"
NEWS_USER_AGENT = "VibeGap/0.1 (vocab-mini-window; non-browser)"
NEWS_REFRESH_MIN = 30      # 拉取间隔,礼貌轮询
NEWS_HTTP_TIMEOUT_SEC = 8
NEWS_POOL_MAX = 60         # 本地新闻池上限(跨多次拉取累积去重,防止十几条来回循环)

# 悬浮窗
WINDOW_WIDTH = 390
WINDOW_HEIGHT = 272
WINDOW_TITLE = "VibeGap"

DICTS_DIR = Path(__file__).resolve().parent.parent / "dicts"  # 源码安装的词书目录

# 各 agent 探测/接入路径(设置面板 Agent 区块 + codex 日志监听)
CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"
CODEX_HOOKS_PATH = Path.home() / ".codex" / "hooks.json"
PI_DIR = Path.home() / ".pi"
DSH_DIR = Path.home() / ".dsh"
WORKBUDDY_SETTINGS_PATH = Path.home() / ".workbuddy-ai" / "settings.json"
CODEX_WATCH_DAYS = 2       # 只高频扫描最近 N 天的日期目录
CODEX_HISTORY_SCAN_SEC = 5  # 低频发现恢复后继续写入旧日期目录的 Codex 对话
CODEX_HISTORY_LOOKBACK_MIN = SESSION_TTL_MIN  # 只接管近期有写入的历史日志

DATA_DIR = Path.home() / ".vibegap"
DB_PATH = DATA_DIR / "vibegap.db"
LOG_DIR = DATA_DIR / "logs"
CONFIG_PATH = DATA_DIR / "config.json"
HOTKEY_PREF_PATH = DATA_DIR / "hotkey.txt"  # 上次注册成功的组合,防止随开机环境漂移


@dataclass(frozen=True)
class Settings:
    """运行时可被 ~/.vibegap/config.json 覆盖的配置项。"""

    popup_delay_sec: int = POPUP_DELAY_SEC
    summary_linger_sec: int = SUMMARY_LINGER_SEC
    session_ttl_min: int = SESSION_TTL_MIN
    daemon_port: int = DAEMON_PORT
    daily_goal: int = 50        # 每日目标词数
    auto_popup: bool = True     # 关闭后 agent 运行不自动弹窗,仅热键/接口手动唤醒
    idle_exit_min: int = IDLE_EXIT_MIN  # 隐藏、无 Agent、无交互后自动退出
    keep_running: bool = False  # 显式选择常驻;默认 False 才能兑现闲置零进程


def load_settings(path: Path = CONFIG_PATH) -> Settings:
    """读用户配置 merge 到默认值;文件缺失或非法值回退默认并警告。"""
    defaults = Settings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return defaults
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("config.json unreadable, using defaults: %s", exc)
        return defaults
    if not isinstance(raw, dict):
        logger.warning("config.json is not an object, using defaults")
        return defaults

    result = defaults
    for field in fields(Settings):
        value = raw.get(field.name)
        if value is None:
            continue
        if isinstance(getattr(defaults, field.name), bool):
            is_valid = isinstance(value, bool)
        else:
            is_valid = isinstance(value, int) and not isinstance(value, bool) and value > 0
        if is_valid:
            result = replace(result, **{field.name: value})
        else:
            logger.warning("config item %s invalid (%r), using default", field.name, value)
    return result
