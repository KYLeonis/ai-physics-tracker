"""应用层日志与科学数据/Undo的边界。"""
from ai_physics_tracker.application.fit_attempts import FitAttempts
from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def test_unsaved_first_save_save_as_and_history_independence(tmp_path):
    session = ProjectSession.start(ProjectRepository())
    history = FitAttempts()
    history.sync(session)
    before = session.project
    history.start({'formula':'a*t','quantity':'x'})
    history.finish('rejected','missing source')
    assert session.project is before
    assert not session.is_dirty
    assert not session.undo()
    root = tmp_path/'saved'
    session.save_as(root)
    history.sync(session)
    first = (root/'analysis/fit-attempts.json').read_bytes()
    assert b'rejected' in first
    destination = tmp_path/'copy'
    session.save_as(destination)
    history.sync(session)
    history.start({'formula':'theta'})
    history.finish('completed','constant fit',solver={'prediction':[1]*100,'residual':[0]*100,'rmse':0.})
    assert (root/'analysis/fit-attempts.json').read_bytes() == first
    assert 'prediction' not in history.journal.attempts[-1]['solver']
    assert not session.is_dirty


def test_switch_project_interrupts_original_and_never_moves_old_attempt(tmp_path):
    first, second = [ProjectSession.start(ProjectRepository()) for _ in range(2)]
    first.save_as(tmp_path/'first')
    second.save_as(tmp_path/'second')
    history = FitAttempts()
    history.sync(first)
    history.start({'formula':'a*t'})
    history.sync(second)
    history.finish('completed','late result')
    assert history.journal.attempts == []
    loaded = FitAttempts(); loaded.sync(first)
    assert loaded.journal.attempts[-1]['status'] == 'interrupted'
