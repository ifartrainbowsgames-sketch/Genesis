from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any

from ..config import settings


@dataclass
class Approval:
    tool: str
    arguments: dict[str, Any]
    expires_at: float


class ApprovalStore:
    def __init__(self) -> None:
        self._items: dict[str, Approval] = {}

    def create(self, tool: str, arguments: dict[str, Any]) -> str:
        self.cleanup()
        approval_id = secrets.token_urlsafe(24)
        self._items[approval_id] = Approval(
            tool=tool,
            arguments=arguments,
            expires_at=time.time() + settings.approval_ttl_seconds,
        )
        return approval_id

    def consume(self, approval_id: str) -> Approval:
        self.cleanup()
        approval = self._items.pop(approval_id, None)
        if not approval:
            raise KeyError("Approval not found or expired")
        return approval

    def cleanup(self) -> None:
        now = time.time()
        expired = [key for key, value in self._items.items() if value.expires_at <= now]
        for key in expired:
            self._items.pop(key, None)


approvals = ApprovalStore()
