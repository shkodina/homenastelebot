from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NasDraft:
    prompt: str
    preview: str
    attachments: list[tuple[str, bytes]] = field(default_factory=list)


_use: set[int] = set()
_nas: set[int] = set()
_drafts: dict[int, NasDraft] = {}


def arm_use(user_id: int) -> None:
    cancel_use(user_id)
    _use.add(user_id)


def arm_nas(user_id: int) -> None:
    cancel_use(user_id)
    _nas.add(user_id)


def cancel_use(user_id: int) -> None:
    _use.discard(user_id)
    _nas.discard(user_id)
    _drafts.pop(user_id, None)


def is_waiting(user_id: int) -> bool:
    return user_id in _use


def is_waiting_nas(user_id: int) -> bool:
    return user_id in _nas


def consume_use(user_id: int) -> bool:
    if user_id not in _use:
        return False
    _use.discard(user_id)
    return True


def consume_nas(user_id: int) -> bool:
    if user_id not in _nas:
        return False
    _nas.discard(user_id)
    return True


def put_nas_draft(user_id: int, draft: NasDraft) -> None:
    _drafts[user_id] = draft


def take_nas_draft(user_id: int) -> NasDraft | None:
    return _drafts.pop(user_id, None)
