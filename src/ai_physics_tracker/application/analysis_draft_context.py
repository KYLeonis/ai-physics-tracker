"""应用层：分析工具「当前草稿」的上下文事实与交付失效判定（Qt-free，R09）。

GLOSSARY「草稿上下文（Draft Context）」的实现载体：只承载瞬时事实并回答
「交付还作不作数」，不保存数值、不持久化、不进入 Undo。事实采集由 GUI 侧
（MainWindow.draftContextFacts）完成；原三份手写清单（导航键、预览输入键的
共享事实部分、源准备迟到核对）统一消费本模块，成员与短路顺序逐一等价
（docs/status/draft-context-plan.md AC-2 对照表）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ai_physics_tracker.application.signal_analysis_job import SignalSelection


@dataclass(frozen=True)
class DraftContextFacts:
    """分析工具页的瞬时导航事实；None 表示部件缺失 / 状态非法的降级值。

    字段与原 MainWindow.analysisNavigationKey 手写元组的成员一一对应；
    便宜采集（纯控件读取），不含需要评估源准备状态的 source_reason。
    """

    workspace: str
    analysis_tab: int | None
    method: int | None
    purpose: str | None
    track_identity: str | None
    quantity: str | None
    source_index: int | None
    history_active: bool


@dataclass(frozen=True)
class NavigationFacts:
    """导航键 = 草稿上下文事实 + 源准备原因（较贵，仅在工具页活动时采集）。"""

    context: DraftContextFacts
    source_reason: str | None


@dataclass(frozen=True)
class SourceDeliveryStamp:
    """源准备任务启动时冻结的草稿上下文与选择；交付时经 source_delivery_stale 核对。"""

    facts: DraftContextFacts
    selection: SignalSelection


def source_delivery_stale(
    stamp: SourceDeliveryStamp,
    facts: DraftContextFacts,
    current_selection: Callable[[], SignalSelection],
) -> bool:
    """源准备交付的迟到核对；成员与求值顺序与迁移前 ChartActions._poll 的手写条件逐位一致。

    current_selection 延迟求值并保持在 workspace 判定之前求值（旧 or 链第 4 位）：
    前三项事实已判迟到时不触碰控件；其抛出的异常仍按原路径传播。
    """
    if (facts.history_active
            or facts.method != stamp.facts.method
            or facts.analysis_tab != stamp.facts.analysis_tab):
        return True
    if current_selection() != stamp.selection:
        return True
    return facts.workspace != stamp.facts.workspace
