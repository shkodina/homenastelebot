from __future__ import annotations

_waiting: set[int] = set()


def arm_use(user_id: int) -> None:
    _waiting.add(user_id)


def cancel_use(user_id: int) -> None:
    _waiting.discard(user_id)


def is_waiting(user_id: int) -> bool:
    return user_id in _waiting


def consume_use(user_id: int) -> bool:
    if user_id not in _waiting:
        return False
    _waiting.discard(user_id)
    return True
