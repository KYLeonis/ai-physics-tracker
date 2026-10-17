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
    history.sync(session, saved=True)
    first = (root/'analysis/fit-attempts.json').read_bytes()
    assert b'rejected' in first
    destination = tmp_path/'copy'
    session.save_as(destination)
    history.sync(session, saved=True)
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


def test_opening_same_identity_copy_loads_its_own_history(tmp_path):
    first=ProjectSession.start(ProjectRepository());first.save_as(tmp_path/'a')
    first.save_as(tmp_path/'b')
    a=ProjectSession.load(ProjectRepository(),tmp_path/'a')
    b=ProjectSession.load(ProjectRepository(),tmp_path/'b')
    history_a,history_b=FitAttempts(),FitAttempts()
    for history,session,formula in ((history_a,a,'A'),(history_b,b,'B')):
        history.sync(session);history.start({'formula':formula});history.finish('failed','test')
    original=(tmp_path/'b/analysis/fit-attempts.json').read_bytes()
    history_a.sync(b)
    assert history_a.journal.attempts[-1]['formula']=='B'
    assert (tmp_path/'b/analysis/fit-attempts.json').read_bytes()==original
