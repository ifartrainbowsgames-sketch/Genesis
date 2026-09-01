from __future__ import annotations

import pytest

from apps.server.app.services import approvals as approvals_module
from apps.server.app.services.approvals import ApprovalStore


def test_approval_is_single_use(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approvals_module.settings, "approval_ttl_seconds", 60)
    monkeypatch.setattr(approvals_module.time, "time", lambda: 1_000.0)
    store = ApprovalStore()

    approval_id = store.create("workspace.write_file", {"path": "safe.txt", "content": "hello"})
    approval = store.consume(approval_id)

    assert approval.tool == "workspace.write_file"
    assert approval.arguments == {"path": "safe.txt", "content": "hello"}

    with pytest.raises(KeyError, match="Approval not found or expired"):
        store.consume(approval_id)


def test_expired_approval_cannot_be_consumed(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 10.0}
    monkeypatch.setattr(approvals_module.settings, "approval_ttl_seconds", 5)
    monkeypatch.setattr(approvals_module.time, "time", lambda: clock["now"])
    store = ApprovalStore()

    approval_id = store.create("workspace.mkdir", {"path": "generated"})
    clock["now"] = 15.0

    with pytest.raises(KeyError, match="Approval not found or expired"):
        store.consume(approval_id)


def test_cleanup_removes_only_expired_approvals(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(approvals_module.settings, "approval_ttl_seconds", 10)
    monkeypatch.setattr(approvals_module.time, "time", lambda: clock["now"])
    store = ApprovalStore()

    expired_id = store.create("workspace.mkdir", {"path": "old"})
    clock["now"] = 105.0
    active_id = store.create("workspace.mkdir", {"path": "new"})
    clock["now"] = 110.0

    store.cleanup()

    with pytest.raises(KeyError):
        store.consume(expired_id)

    active = store.consume(active_id)
    assert active.arguments == {"path": "new"}
