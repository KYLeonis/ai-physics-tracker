"""应用层 AI 环境用例入口；GUI 不直接访问安装基础设施。"""

from ai_physics_tracker.infrastructure.runtime_install import (
    RuntimeProgress,
    RuntimeCancellation,
    install_runtime,
    load_profiles,
    profile_supported,
    verify_runtime,
)
