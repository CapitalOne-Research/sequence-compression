"""Timestamp-to-epoch decoder. See c1/aiml/compression/encoding_schemes.md."""

from datetime import datetime, timezone


def decode(values: list[int]) -> list[str]:
    result = []
    for v in values:
        dt = datetime.fromtimestamp(v / 1000, tz=timezone.utc).replace(tzinfo=None)
        ms = dt.microsecond // 1000
        result.append(dt.strftime('%Y-%m-%d %H:%M:%S.') + f'{ms:03d}'.rstrip('0'))
    return result
