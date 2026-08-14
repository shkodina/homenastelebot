from __future__ import annotations


def is_allowed(user_id: int, allowed_ids: frozenset[int]) -> bool:
    return user_id in allowed_ids
