from typing import Any
import json

from c1.aiml.compression.utils.sizing import get_json_byte_size, _ensure_list, convert_to_json
from c1.aiml.compression.utils.lookup import ENCODING_SCHEMES, ENCODE_PARAMS
from c1.aiml.compression.encoding.auto_encode import auto_encode


def encode_feature_df(df, encoding_schema: dict = None, drop_originals: bool = True, metrics: bool = False, lossy: bool = True):
    """
    Encode a DataFrame of features using the specified encoding scheme.

    Args:
        df: The DataFrame to encode
        encoding_schema: The encoding schema to use
        drop_originals: Whether to drop the original columns
        metrics: Whether to include metrics in the output

    Returns:
        The encoded DataFrame
    """
    import pandas as pd
    records = df.to_dict('records')
    total = len(records)
    encoded_feature_dicts = []
    for i, feature_dict in enumerate(records):
        if (i + 1) % 100 == 0 or (i + 1) == total:
            print(f"Encoding rows: {i + 1}/{total}")
        encoded_feature_dicts.append(
            encode_feature_payload(feature_dict, encoding_schema, metrics=metrics, lossy=lossy)
        )


    encoded_df = pd.DataFrame(encoded_feature_dicts)

    if not drop_originals:
        # Add encoded columns to the original DataFrame
        new_cols = [col for col in encoded_df.columns if col not in df.columns]
        result_df = df.copy()
        for col in new_cols:
            result_df[col] = encoded_df[col].values
        return result_df

    return encoded_df

def encode_feature_payload(payload: dict, encoding_schema: dict=None, metrics=False, lossy: bool = True) -> dict:
    """
    Encode a feature payload using the specified encoding scheme.

    Args:
        payload: The payload to encode
        encoding_schema: The encoding schema to use
        metrics: Whether to include metrics in the output

    Returns:
        The encoded payload
    """
    if encoding_schema is None:
        encoding_schema = {
            name: "auto" for name, value in payload.items()
            if isinstance(value, list) or hasattr(value, 'tolist')
        }

    encoded_payload = {}
    for feature_name, feature_value in payload.items():
        feature_encoding_scheme = encoding_schema.get(feature_name, [])
        if not feature_encoding_scheme:
            encoded_value, encoding_scheme, auxiliary_info = feature_value, None, {}
        elif feature_encoding_scheme == "auto":
            encoded_value, encoding_scheme, auxiliary_info = auto_encode(feature_value, lossy=lossy)
        elif isinstance(feature_encoding_scheme, list):
            encoded_value, encoding_scheme, auxiliary_info = evaluate_candidates(feature_value, feature_encoding_scheme)
        else:
            encoded_value, encoding_scheme, auxiliary_info = encode_feature(feature_value, feature_encoding_scheme)

        entry = [encoded_value]
        if encoding_scheme:
            entry.append(encoding_scheme)
        if auxiliary_info:
            entry.append(auxiliary_info)
        encoded_payload[f'{feature_name}_enc'] = convert_to_json(entry)

    if metrics:
        encoded_payload['encoded_size'] = get_json_byte_size(encoded_payload)
        encoded_payload['payload_size'] = get_json_byte_size(payload)

    return encoded_payload

def encode_feature(feature_value, encoding_scheme: str) -> tuple[Any, str, dict]:
    """
    Encode a feature value using the specified encoding scheme.

    Args:
        feature_value: The value to encode
        encoding_scheme: The encoding scheme to use
    Returns:
        The encoded feature value(s) - may be a single value or tuple depending on encoders
    """
    if not encoding_scheme:
        return feature_value, "", {}
    feature_value = _ensure_list(feature_value)

    original_value = feature_value
    auxillary_info = {}
    for step in encoding_scheme.split("_"):
        feature_value, new_auxiliary_info = ENCODING_SCHEMES[step].encode(feature_value)
        auxillary_info.update(new_auxiliary_info)

    # Only use encoded result if it actually reduces size
    original_size = get_json_byte_size([original_value])
    encoded_entry = [feature_value, encoding_scheme]
    if auxillary_info:
        encoded_entry.append(auxillary_info)
    encoded_size = get_json_byte_size(encoded_entry)
    if encoded_size >= original_size:
        return original_value, "", {}

    return feature_value, encoding_scheme, auxillary_info

def evaluate_candidates(values: list, candidates: list[str], cache=True) -> tuple[Any, dict, str]:
    """Encode values through a pipeline, reusing cached intermediate results.

    This function evaluates multiple encoding candidates and returns the best one.

    When multiple candidates share a prefix (e.g., cat_rle, cat_bp, cat),
    the shared first step is encoded once and cached.

    Args:
        values: Original input values.
        candidates: List of encoding step names.
        cache: Whether to cache intermediate results.

    Returns:
        Tuple of (encoded_value, auxiliary_info, encoding_scheme_string).
    """
    values = _ensure_list(values)

    if cache:
        prefix_cache: dict[str, tuple] = {}  # step -> (encoded_value, aux_info)

    # Encode each candidate, caching shared prefixes
    best_encoded = values
    best_aux = {}
    best_enc = None
    best_size = get_json_byte_size([values])


    for option in candidates:
        steps = option.split('_')
        current = values
        auxiliary_info = {}

        for i, step in enumerate(steps):
            if not cache:
                current, new_aux = ENCODING_SCHEMES[step].encode(current)
                auxiliary_info.update(new_aux)
                continue
            # Build a cache key from the prefix of steps up to and including this one
            cache_key = "_".join(steps[:i + 1])

            if cache_key in prefix_cache:
                current, cached_aux = prefix_cache[cache_key]
                auxiliary_info.update(cached_aux)
            else:
                current, new_aux = ENCODING_SCHEMES[step].encode(current)
                auxiliary_info.update(new_aux)
                prefix_cache[cache_key] = (current, dict(auxiliary_info))

            # Use the prefix of steps actually applied, not the full candidate
            current_enc = "_".join(steps[:i + 1])
            encoded_entry = [current, current_enc]
            if auxiliary_info:
                encoded_entry.append(auxiliary_info)
            payload_size = get_json_byte_size(encoded_entry)
            if payload_size < best_size:
                best_encoded = current
                best_aux = dict(auxiliary_info)
                best_enc = current_enc
                best_size = payload_size

    return best_encoded, best_enc, best_aux
