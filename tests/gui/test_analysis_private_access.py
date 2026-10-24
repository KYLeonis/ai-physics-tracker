"""R09 回归：分析簇跨模块私有穿越清零（AC-3，源文本扫描）。

覆盖计划枚举的访问集（docs/status/draft-context-plan.md Scope 第 4 条）；
signal_history 对 panel 的其余历史遗留访问（_loading / _methodVisibility /
_video_id / _eventLines / _eventSamplesMatch / _referenceChanged）为已记录的
遗留项，不在本轮清单内，不由本测试守卫。
"""

import re
from pathlib import Path

GUI_ROOT = Path(__file__).resolve().parents[2] / "src" / "ai_physics_tracker" / "gui"

# 文件 →（描述, 禁止模式）；模式针对已枚举的私有字段 / 方法名，避免误伤其他合法下划线属性。
FORBIDDEN_PATTERNS: dict[str, tuple[tuple[str, str], ...]] = {
    "signal_preview.py": (
        ("panel 视图状态私有字段", r"panel\._(valueRange|previewRange|eventPreview|allowCachedEvents|viewingDiskSaved)"),
        ("ChartActions 私有状态 / 方法", r"actions\._(closed|signal_job|prepareSignal)\b"),
    ),
    "signal_history.py": (
        ("panel 视图状态私有字段", r"\bp\._(valueRange|previewRange|allowCachedEvents|viewingDiskSaved)"),
        ("panel 视图状态私有字段", r"panel\._(valueRange|previewRange|allowCachedEvents|viewingDiskSaved)"),
        ("ChartActions / SignalPreview 私有状态", r"(actions|preview)\._(executor|closed|signal_job|prepareSignal)\b"),
    ),
    "chart_actions.py": (
        ("SignalAnalysisPanel 私有字段", r"signalPanel\._"),
        ("SignalPreview 私有字段", r"\.preview\._"),
        ("MainWindow 私有方法", r"window\._analysisMethodChanged"),
    ),
    "main_window.py": (
        ("TrackingActions 私有工作流状态", r"trackingActions\._current_workflow_state"),
    ),
}


def test_analysis_cluster_has_no_enumerated_cross_module_private_access():
    for filename, checks in FORBIDDEN_PATTERNS.items():
        text = (GUI_ROOT / filename).read_text(encoding="utf-8")
        for description, pattern in checks:
            match = re.search(pattern, text)
            assert match is None, (
                f"{filename} 残留跨模块私有访问（{description}）: {match.group(0) if match else pattern}")
