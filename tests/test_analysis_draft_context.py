"""R09：草稿上下文事实与源准备迟到判定的 Qt-free 单测（AC-4）。

事实成员与原三份手写清单一一对应（docs/status/draft-context-plan.md AC-2）；
迟到判定的分支与短路顺序覆盖 chart_actions._poll 迁移前的每个条件。
"""

from uuid import uuid4

from ai_physics_tracker.application.analysis_draft_context import (
    DraftContextFacts,
    NavigationFacts,
    SourceDeliveryStamp,
    source_delivery_stale,
)
from ai_physics_tracker.application.signal_analysis_job import SignalSelection


def _facts(**overrides) -> DraftContextFacts:
    members = dict(
        workspace="analysis",
        analysis_tab=1,
        method=0,
        purpose="fit",
        track_identity="track-a",
        quantity="x",
        source_index=0,
        history_active=False,
    )
    members.update(overrides)
    return DraftContextFacts(**members)


def _selection(end_frame: int = 10) -> SignalSelection:
    return SignalSelection(track_id=uuid4(), quantity="x", start_frame=0, end_frame=end_frame)


def test_facts_equal_only_when_all_navigation_members_match():
    baseline = _facts()
    same = _facts()
    assert baseline == same
    for member, other in (
        ("workspace", "acquire"),
        ("analysis_tab", 0),
        ("analysis_tab", None),
        ("method", 1),
        ("method", None),
        ("purpose", "measure"),
        ("purpose", None),
        ("track_identity", "track-b"),
        ("track_identity", None),
        ("quantity", "theta"),
        ("quantity", None),
        ("source_index", 1),
        ("source_index", None),
        ("history_active", True),
    ):
        assert baseline != _facts(**{member: other}), member


def test_navigation_facts_comparison_includes_source_reason():
    context = _facts()
    assert NavigationFacts(context=context, source_reason=None) == NavigationFacts(
        context=context, source_reason=None)
    assert NavigationFacts(context=context, source_reason=None) != NavigationFacts(
        context=context, source_reason="Source not prepared")


def test_delivery_fresh_when_context_and_selection_unchanged():
    selection = _selection()
    stamp = SourceDeliveryStamp(facts=_facts(), selection=selection)
    assert source_delivery_stale(stamp, _facts(), lambda: selection) is False


def test_delivery_stale_on_each_context_change():
    selection = _selection()
    for member, other in (
        ("history_active", True),
        ("method", 1),
        ("analysis_tab", 0),
        ("workspace", "acquire"),
    ):
        stamp = SourceDeliveryStamp(facts=_facts(), selection=selection)
        assert source_delivery_stale(stamp, _facts(**{member: other}), lambda: selection) is True, member


def test_delivery_stale_when_selection_changed():
    stamp = SourceDeliveryStamp(facts=_facts(), selection=_selection(end_frame=10))
    assert source_delivery_stale(stamp, _facts(), lambda: _selection(end_frame=20)) is True


def test_delivery_stale_short_circuits_before_reading_selection():
    """前三项事实已判迟到时不再触碰控件，与原 or 链前三位短路一致。"""

    def forbidden() -> SignalSelection:
        raise AssertionError("selection must not be read when facts already stale")

    stamp = SourceDeliveryStamp(facts=_facts(), selection=_selection())
    for member, other in (
        ("history_active", True),
        ("method", 1),
        ("analysis_tab", 0),
    ):
        assert source_delivery_stale(stamp, _facts(**{member: other}), forbidden) is True, member


def test_delivery_stale_reads_selection_before_workspace_verdict():
    """selection 求值保持在 workspace 判定之前（旧 or 链第 4 位）。

    workspace 已变但 selection() 抛异常时，异常仍按原路径传播，
    不得被 workspace 判定吞掉换成迟到结论。
    """

    def invalid() -> SignalSelection:
        raise ValueError("Select a track")

    stamp = SourceDeliveryStamp(facts=_facts(), selection=_selection())
    try:
        source_delivery_stale(stamp, _facts(workspace="acquire"), invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("selection error must propagate before workspace verdict")
    assert source_delivery_stale(stamp, _facts(workspace="acquire"), lambda: stamp.selection) is True
