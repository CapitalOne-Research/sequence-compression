import json

from c1.aiml.compression.utils.lookup import DECODE_PARAMS, DECODING_SCHEMES

def decode_feature_payload(payload: dict) -> dict:
    """
    Decode a feature payload using the specified decoding scheme.

    Args:
        payload: The payload to decode

    Returns:
        The decoded payload
    """
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

        decoded_payload[feature_name] = decode_feature(
            encoded_feature_arr[0],
            encoded_feature_arr[1] if len(encoded_feature_arr) > 1 else "",
            encoded_feature_arr[2] if len(encoded_feature_arr) > 2 else {},
        )
    return decoded_payload

def decode_feature(feature_value, encoding_scheme: str = None, auxiliary_info: dict = None) -> list:
    """
    Decode a feature value using the specified decoding scheme.
    
    Args:
        feature_value: The value to decode
        encoding_scheme: The encoding scheme to use
        auxiliary_info: Optional dict of auxiliary info from decoding
    Returns:
        The decoded feature value
    """
    if not encoding_scheme:
        return feature_value
    decoding_steps = encoding_scheme.split('_')[::-1]
    for step in decoding_steps:
        decode_func = DECODING_SCHEMES[step].decode
        params = DECODE_PARAMS[step]
        kwargs = {k: auxiliary_info[k] for k in params if k in auxiliary_info}
        
        feature_value = decode_func(feature_value, **kwargs)

    return feature_value