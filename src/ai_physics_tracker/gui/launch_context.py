"""组合根的运行环境解析（P6.1：frozen 应用 / source dev 两形态）。

dev（source checkout）形态：runtime python = 当前解释器；FFprobe 走 PATH
（``FFprobeTimingProbe(None)`` 的既有行为）。

frozen（PyInstaller onedir）形态：
- 资源根 = ``sys._MEIPASS/resources``（FFprobe 二进制、worker 源码、许可文本）；
- runtime python 优先级：``AI_PHYSICS_RUNTIME_PYTHON``（测试后门/高级用户）
  → managed runtime 指针（P6.2 安装器合同，本阶段只读不安装）
  → ``None``（调用方显示"安装 AI 环境"占位，绝不用 frozen host 自身充当
    Python worker，也不导入开发 venv）。

Qt 依赖说明：AppDataLocation 语义需要 ``QApplication`` 已设置应用名；本模块
只被组合根与 GUI 控制器使用，调用前 ``gui.app.run`` 已完成命名（模块级静态
setter 在 QApplication 构造前亦生效）。
"""

import logging
import os
from pathlib import Path
import sys

from PySide6.QtCore import QStandardPaths

logger = logging.getLogger(__name__)

APP_NAME = "AI Physics Tracker"
ORG_NAME = "KYLeonis"

# managed runtime 指针（P6.2 前的只读约定）：<AppDataLocation>/runtimes/active.txt
# 首行为 AI runtime 解释器的绝对路径。安装器负责原子写指针；host 只读取并校验。
RUNTIME_POINTER_RELATIVE = Path("runtimes") / "active.txt"

# frozen 分离红线：host 进程禁止导入的顶层包（冒烟测试断言同一集合）
FORBIDDEN_HOST_ROOTS = ("torch", "torchvision", "deeplabcut")


def set_application_identity() -> None:
    """设置 Qt 应用身份；必须在任何路径解析/QApplication 创建之前调用。

    QStandardPaths 的 AppDataLocation 依赖 applicationName/organizationName；
    晚于文件日志/managed runtime 指针解析设置会得到通用目录（P6.1 构建实测
    曾把日志写到 ``~/Library/Application Support/logs``）。
    """

    from PySide6.QtCore import QCoreApplication

    QCoreApplication.setApplicationName(APP_NAME)
    QCoreApplication.setOrganizationName(ORG_NAME)


def is_frozen() -> bool:
    """PyInstaller frozen 判定（onedir/windowed 均设置 ``sys.frozen``）。"""

    return bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")


def resource_root() -> Path | None:
    """frozen 资源根（``_MEIPASS/resources``）；dev 返回 ``None``。"""

    if not is_frozen():
        return None
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        return None
    return Path(base) / "resources"


def bundled_ffprobe() -> Path | None:
    """随包分发的 FFprobe 绝对路径；dev 或缺失时返回 ``None``（回退 PATH）。"""

    root = resource_root()
    if root is None:
        return None
    name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    candidate = root / "ffprobe" / name
    return candidate if candidate.is_file() else None


def worker_package_root() -> Path | None:
    """external worker 的受信源码根（含 ``ai_physics_tracker/``）；dev 为 ``None``。

    frozen host 的 ``external_worker._default_package_root`` 会指进 PyInstaller
    归档,不是子进程可导入的源码树;训练/自检/推理必须显式传本根。
    """

    root = resource_root()
    if root is None:
        return None
    candidate = root / "worker-src"
    return candidate if (candidate / "ai_physics_tracker" / "worker" / "__main__.py").is_file() else None


def app_data_dir() -> Path:
    """用户应用数据目录（QStandardPaths AppDataLocation 语义）。"""

    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )
    if location:
        return Path(location)
    # Qt 无法定位时（无应用实例等）退回平台默认，保证诊断/日志仍可写；
    # 目录层级与 QStandardPathsWith org/app 的一致
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / ORG_NAME / APP_NAME
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        windows_root = Path(base) if base else home / "AppData" / "Roaming"
        return windows_root / ORG_NAME / APP_NAME
    return home / ".local" / "share" / ORG_NAME / APP_NAME


def runtime_python() -> str | None:
    """解析 external worker 的解释器路径；frozen 且无可用 runtime 时为 ``None``。

    dev 恒为 ``sys.executable``（现有行为的唯一来源）；frozen 只接受显式
    env 覆盖或 managed runtime 指针，二者都必须指向真实存在的文件。
    """

    if not is_frozen():
        return sys.executable
    override = os.environ.get("AI_PHYSICS_RUNTIME_PYTHON")
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file():
            return str(candidate)
        logger.warning(
            "AI_PHYSICS_RUNTIME_PYTHON=%s is not an existing file; ignoring", override
        )
    pointer = app_data_dir() / RUNTIME_POINTER_RELATIVE
    try:
        first_line = pointer.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        return None
    if not first_line:
        return None
    candidate = Path(first_line).expanduser()
    if candidate.is_file():
        return str(candidate)
    logger.warning(
        "managed runtime pointer %s references missing interpreter %s",
        pointer,
        first_line,
    )
    return None


def runtime_status_detail() -> str:
    """占位提示的具体原因（写入"安装 AI 环境"消息框，便于诊断）。"""

    if is_frozen() and os.environ.get("AI_PHYSICS_RUNTIME_PYTHON"):
        return (
            "The AI_PHYSICS_RUNTIME_PYTHON override is set but does not point to "
            "an existing Python interpreter."
        )
    pointer = app_data_dir() / RUNTIME_POINTER_RELATIVE
    return (
        "No managed AI runtime is installed for this application "
        f"(expected at {pointer})."
    )


def log_dir() -> Path:
    return app_data_dir() / "logs"


def configure_file_logging() -> Path | None:
    """frozen 形态下把 root logger 追加写入应用数据目录；dev 返回 ``None``。

    只在 frozen 启动时调用一次；失败不阻断启动（GUI 仍可用，仅无文件日志）。
    """

    if not is_frozen():
        return None
    try:
        target = log_dir()
        target.mkdir(parents=True, exist_ok=True)
        path = target / "app.log"
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s: %(message)s"
            )
        )
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)
        return path
    except OSError as error:
        logger.warning("could not configure file logging: %s", error)
        return None


def show_ai_runtime_missing(window) -> None:
    """AI 入口在 frozen 且无可用 runtime 时的统一占位提示（P6.2 前的 setup 占位）。"""

    from PySide6.QtWidgets import QMessageBox

    QMessageBox.information(
        window,
        "AI environment is not installed",
        "<p>Training and AI inference need the separate AI runtime, which is not "
        "installed with this build.</p>"
        "<p>Manual tracking, calibration, analysis and export keep working with the "
        "features available now.</p>"
        f"<p>{runtime_status_detail()}</p>",
    )
