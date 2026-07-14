"""Timestamp-to-epoch encoder. See c1/aiml/compression/encoding_schemes.md."""

from datetime import datetime, timezone


def encode(values: list[str]) -> tuple[list[int], dict]:
    if len(values) == 0:
        return [], {}

    result = []
    for v in values:
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        result.append(round(dt.timestamp() * 1000))
    return result, {}
