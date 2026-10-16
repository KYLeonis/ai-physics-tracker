"""拟合尝试日志持久化测试。"""

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from ai_physics_tracker.infrastructure import fit_attempt_journal
from ai_physics_tracker.infrastructure.fit_attempt_journal import FitAttemptJournal


def _path(root: Path) -> Path:
    return root / "analysis" / "fit-attempts.json"


def _payload(root: Path) -> dict[str, object]:
    return json.loads(_path(root).read_text(encoding="utf-8"))


def test_success_lifecycle_persists_running_then_finished_summary(tmp_path: Path) -> None:
    root = tmp_path / "project"
    journal = FitAttemptJournal("project-1")
    assert journal.project_id == "project-1"
    journal.add({"status": "running", "formula": "a*t+b"})
    attempt_id = journal.attempts[0]["id"]

    journal.bind(root)
    journal.finish(
        attempt_id,
        status="completed",
        finished_at="2026-10-16T08:00:00+00:00",
        result={"rmse": 0.01},
    )

    reopened = FitAttemptJournal("project-1", root)
    assert reopened.attempts == [
        {
            "status": "completed",
            "formula": "a*t+b",
            "id": attempt_id,
            "finished_at": "2026-10-16T08:00:00+00:00",
            "result": {"rmse": 0.01},
        }
    ]
    assert _payload(root)["project_id"] == "project-1"


@pytest.mark.parametrize("status", ["rejected", "failed", "cancelled"])
def test_rejection_failure_and_cancel_summaries_round_trip(
    tmp_path: Path, status: str
) -> None:
    root = tmp_path / status
    journal = FitAttemptJournal("p")
    journal.bind(root)
    journal.add({"status": status, "reason": f"{status} reason"})

    reopened = FitAttemptJournal("p", root)
    assert reopened.attempts[0]["status"] == status
    assert reopened.attempts[0]["reason"] == f"{status} reason"


def test_unsaved_bind_and_save_as_leave_previous_root_unchanged(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    journal = FitAttemptJournal("p")
    journal.add({"status": "running", "formula": "a*t"})
    journal.bind(first_root)
    before_save_as = _path(first_root).read_bytes()

    journal.bind(second_root)

    assert _path(first_root).read_bytes() == before_save_as
    assert _payload(second_root)["attempts"] == journal.attempts


def test_unknown_version_mismatch_and_corrupt_files_are_preserved_read_only(
    tmp_path: Path,
) -> None:
    cases = (
        ("version", {"version": 999, "project_id": "p", "attempts": []}),
        ("mismatch", {"version": 1, "project_id": "other", "attempts": []}),
        ("corrupt", b'{"version": 1, "project_id": "p",'),
    )

    for name, content in cases:
        root = tmp_path / name
        path = _path(root)
        path.parent.mkdir(parents=True)
        raw = content if isinstance(content, bytes) else json.dumps(content).encode()
        path.write_bytes(raw)

        journal = FitAttemptJournal("p", root)
        journal.add({"status": "running"})
        journal.retry()

        assert journal.read_only
        assert journal.warning
        assert path.read_bytes() == raw


def test_unknown_top_level_and_attempt_fields_survive_update(tmp_path: Path) -> None:
    root = tmp_path / "project"
    path = _path(root)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "project_id": "p",
                "future_top_level": {"enabled": True},
                "attempts": [
                    {
                        "id": "a1",
                        "status": "running",
                        "future_attempt": [1, 2, 3],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    journal = FitAttemptJournal("p", root)
    journal.finish("a1", status="completed")
    payload = _payload(root)

    assert payload["future_top_level"] == {"enabled": True}
    assert payload["attempts"][0]["future_attempt"] == [1, 2, 3]


def test_reopened_running_entries_are_interrupted_and_persisted(tmp_path: Path) -> None:
    root = tmp_path / "project"
    path = _path(root)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "project_id": "p",
                "attempts": [{"id": "a1", "status": "running"}],
            }
        ),
        encoding="utf-8",
    )

    journal = FitAttemptJournal("p", root)
    entry = journal.attempts[0]

    assert entry["status"] == "interrupted"
    assert "interrupted" in str(entry["reason"]).lower()
    finished_at = datetime.fromisoformat(str(entry["finished_at"]))
    assert finished_at.tzinfo is not None
    assert finished_at.utcoffset() == UTC.utcoffset(finished_at)
    assert _payload(root)["attempts"][0]["status"] == "interrupted"


def test_io_failure_keeps_memory_and_retry_can_persist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "project"
    journal = FitAttemptJournal("p")
    journal.bind(root)

    real_replace = fit_attempt_journal.os.replace
    calls = 0

    def fail_once(source: str | bytes | Path, destination: str | bytes | Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("simulated replace failure")
        real_replace(source, destination)

    monkeypatch.setattr(fit_attempt_journal.os, "replace", fail_once)
    journal.add({"status": "failed", "reason": "solver error"})

    assert journal.attempts[0]["reason"] == "solver error"
    assert not journal.read_only
    assert "retry" in journal.warning.lower()

    journal.retry()

    assert journal.warning == ""
    assert _payload(root)["attempts"] == journal.attempts


def test_external_modification_conflict_keeps_disk_bytes_and_becomes_read_only(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    journal = FitAttemptJournal("p")
    journal.bind(root)
    journal.add({"status": "completed", "id": "a1"})

    external = b'{"external": true}\n'
    _path(root).write_bytes(external)
    journal.add({"status": "failed", "id": "a2"})
    journal.retry()

    assert journal.read_only
    assert "externally" in journal.warning.lower()
    assert _path(root).read_bytes() == external


def test_non_finite_attempt_values_are_rejected_before_persistence(tmp_path: Path) -> None:
    journal = FitAttemptJournal("p", tmp_path / "project")

    with pytest.raises(ValueError, match="JSON-safe"):
        journal.add({"status": "failed", "rmse": float("nan")})



@pytest.mark.parametrize('attempt',[{'id':'a','formula':7},{'id':'a','elapsed_s':'oops'}, {'status':'failed'}])
def test_malformed_known_attempt_fields_preserve_original_read_only(tmp_path,attempt):
    root=tmp_path/'project'; path=root/'analysis/fit-attempts.json'
    path.parent.mkdir(parents=True)
    original=json.dumps({'version':1,'project_id':'p','attempts':[attempt]}).encode()
    path.write_bytes(original)
    journal=FitAttemptJournal('p',root)
    assert journal.read_only
    journal.add({'formula':'x','status':'rejected'})
    assert path.read_bytes()==original


def test_initial_read_failure_can_be_retried_without_losing_memory(tmp_path):
    root=tmp_path/'p';root.mkdir();(root/'analysis').write_text('blocked')
    journal=FitAttemptJournal('p',root)
    journal.add({'id':'new','status':'failed'})
    assert journal.warning and not journal.read_only
    (root/'analysis').unlink();(root/'analysis').mkdir()
    journal.retry()
    assert not journal.warning
    assert _payload(root)['attempts'][0]['id']=='new'


def test_duplicate_or_missing_status_rejected_before_disk_change(tmp_path):
    journal=FitAttemptJournal('p',tmp_path)
    journal.add({'id':'a','status':'failed'})
    before=(tmp_path/'analysis/fit-attempts.json').read_bytes()
    for attempt in ({'id':'a','status':'failed'},{'id':'b'}):
        with pytest.raises(ValueError):journal.add(attempt)
    assert (tmp_path/'analysis/fit-attempts.json').read_bytes()==before


def test_read_retry_preserves_recovered_extensions_and_appends_memory(tmp_path):
    root=tmp_path/'p';root.mkdir();(root/'analysis').write_text('blocked')
    journal=FitAttemptJournal('p',root)
    journal.add({'id':'new','status':'failed'})
    (root/'analysis').unlink();(root/'analysis').mkdir()
    payload={'version':1,'project_id':'p','future':{'keep':3},'attempts':[{'id':'old','status':'completed','future':True}]}
    (root/'analysis/fit-attempts.json').write_text(json.dumps(payload))
    journal.retry()
    loaded=_payload(root)
    assert loaded['future']=={'keep':3}
    assert [item['id'] for item in loaded['attempts']]==['old','new']
    assert loaded['attempts'][0]['future'] is True


def test_bind_never_overwrites_diverged_same_project_history(tmp_path):
    a,b=tmp_path/'a',tmp_path/'b'
    first,second=FitAttemptJournal('p',a),FitAttemptJournal('p',b)
    first.add({'id':'a','status':'failed'})
    second.add({'id':'b','status':'failed','future':'keep'})
    before=(b/'analysis/fit-attempts.json').read_bytes()
    first.bind(b)
    assert first.read_only
    assert (b/'analysis/fit-attempts.json').read_bytes()==before
