from __future__ import annotations

import json
from typing import Any

from seqpack.exceptions import DecodingError, InvalidInputError, UnknownSchemeError
from seqpack.utils.lookup import DECODE_PARAMS, DECODING_SCHEMES
from seqpack.wire import EncodedEntry

def decode_feature_payload(payload: dict) -> dict:
    """
    Decode a feature payload using the specified decoding scheme.

    Args:
        payload: The payload to decode

    Raises:
        InvalidInputError: If `payload` is not a dict.
        DecodingError: If an `*_enc` entry isn't a valid wire-format record.

    Returns:
        The decoded payload
    """
    if not isinstance(payload, dict):
        raise InvalidInputError(f"payload must be a dict, got {type(payload).__name__}")

    decoded_payload = {}
    for encoded_feature_name, encoded_feature_arr in payload.items():
        if not encoded_feature_name.endswith('_enc'):
            continue
        feature_name = encoded_feature_name[:-len('_enc')]
        if isinstance(encoded_feature_arr, str):
            encoded_feature_arr = json.loads(encoded_feature_arr)
        # Handle double-encoded JSON strings
        if isinstance(encoded_feature_arr, str):
            encoded_feature_arr = json.loads(encoded_feature_arr)

        if not isinstance(encoded_feature_arr, list) or not encoded_feature_arr:
            raise DecodingError(
                f"'{encoded_feature_name}' is not a valid wire-format record "
                f"(expected a non-empty list, got {type(encoded_feature_arr).__name__})"
            )

        entry = EncodedEntry.from_wire(encoded_feature_arr)
        decoded_payload[feature_name] = decode_feature(entry.value, entry.scheme, entry.aux)
    return decoded_payload

def decode_feature(feature_value: Any, encoding_scheme: str | None = None, auxiliary_info: dict | None = None) -> Any:
    """
    Decode a feature value using the specified decoding scheme.

    Args:
        feature_value: The value to decode
        encoding_scheme: The encoding scheme to use
        auxiliary_info: Optional dict of auxiliary info from decoding

    Raises:
        UnknownSchemeError: If `encoding_scheme` contains a step that is not a
            registered decoding scheme.

    Returns:
        The decoded feature value. When `encoding_scheme` is falsy,
        `feature_value` is returned unchanged.
    """
    if not encoding_scheme:
        return feature_value
    auxiliary_info = auxiliary_info or {}
    decoding_steps = encoding_scheme.split('_')[::-1]
    for step in decoding_steps:
        if step not in DECODING_SCHEMES:
            valid = ", ".join(sorted(DECODING_SCHEMES))
            raise UnknownSchemeError(f"Unknown decoding step '{step}'. Valid steps: {valid}")
        decode_func = DECODING_SCHEMES[step].decode
        params = DECODE_PARAMS[step]
        kwargs = {k: auxiliary_info[k] for k in params if k in auxiliary_info}

        feature_value = decode_func(feature_value, **kwargs)

    return feature_value
