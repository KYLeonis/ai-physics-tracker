"""应用层：拟合尝试的工程归属、运行状态和独立日志生命周期。"""

from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.infrastructure.fit_attempt_journal import FitAttemptJournal


class FitAttempts:
    """不修改Project或Undo；调用方在GUI主线程串行操作。"""

    def __init__(self) -> None:
        self.journal: FitAttemptJournal | None = None
        self._active_id: str | None = None
        self._started: float | None = None

    @property
    def active(self) -> bool:
        return self._active_id is not None

    @property
    def elapsed_s(self) -> float:
        return monotonic()-self._started if self._started is not None else 0.0

    def sync(self, session: ProjectSession | None) -> None:
        """在保存完成后绑定新路径；切工程前结束原工程的尝试。"""
        identity = str(session.project.project_id) if session else None
        if self.journal is not None and self.journal.project_id != identity:
            self.interrupt()
            self.journal = None
        if session is not None:
            if self.journal is None:
                self.journal = FitAttemptJournal(identity, session.project_root)
            else:
                self.journal.bind(session.project_root)

    def start(self, recipe: dict) -> None:
        """保留输入原文，哪怕后续同步校验拒绝，也能解释本次请求。"""
        if self.journal is None:
            return
        self._active_id = str(uuid4())
        self._started = monotonic()
        self.journal.add(recipe | {"id": self._active_id, "status": "running",
                                   "started_at": datetime.now(timezone.utc).isoformat()})

    def annotate(self, **updates) -> None:
        """补入通过准备校验后才可获得的源身份，不改变终态。"""
        if self.journal is not None and self._active_id is not None:
            self.journal.finish(self._active_id, **updates)

    def finish(self, status: str, reason: str, **updates) -> None:
        """只记简要求解信息，不复制每次预测/残差数组。"""
        if self.journal is None or self._active_id is None:
            return
        for key in ("solver", "summary"):
            if key in updates:
                updates[key] = {name: value for name, value in updates[key].items()
                                if name not in ("prediction", "residual", "events", "intervals_s")}
        self.journal.finish(self._active_id, status=status, reason=reason,
                            finished_at=datetime.now(timezone.utc).isoformat(), elapsed_s=self.elapsed_s, **updates)
        self._active_id = None

    def interrupt(self) -> None:
        """关闭或切上下文时在原日志终结在途请求，不接受晚到结果。"""
        self.finish("interrupted", "Context / window changed; pending result discarded")
        if self.journal is not None:
            self.journal.interrupt()
