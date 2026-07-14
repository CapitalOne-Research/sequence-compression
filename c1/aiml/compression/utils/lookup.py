import importlib
import inspect

_ENCODING_NAMES = {
    "bm": "bm_encoding",
    "bp": "bp_encoding",
    "cat": "cat_encoding",
    "del": "delta_encoding",
    "nbp": "nbp_encoding",
    "quant": "quant_encoding",
    "rle": "rle_encoding",
    "stl": "stl_encoding",
    "tbqm": "tbqm_encoding",
    "tbqp": "tbqp_encoding",
}

_DECODING_NAMES = {
    "bm": "bm_decoding",
    "bp": "bp_decoding",
    "cat": "cat_decoding",
    "del": "delta_decoding",
    "nbp": "nbp_decoding",
    "quant": "quant_decoding",
    "rle": "rle_decoding",
    "stl": "stl_decoding",
    "tbqm": "tbqm_decoding",
    "tbqp": "tbqp_decoding",
}

ENCODING_SCHEMES = {
    short: importlib.import_module(f"c1.aiml.compression.encoding.schemes.{name}")
    for short, name in _ENCODING_NAMES.items()
}

DECODING_SCHEMES = {
    short: importlib.import_module(f"c1.aiml.compression.decoding.schemes.{name}")
    for short, name in _DECODING_NAMES.items()
}

ENCODE_PARAMS: dict[str, list[str]] = {
    name: list(inspect.signature(module.encode).parameters.keys())[1:]
    for name, module in ENCODING_SCHEMES.items()
}

DECODE_PARAMS: dict[str, list[str]] = {
    name: list(inspect.signature(module.decode).parameters.keys())[1:]
    for name, module in DECODING_SCHEMES.items()
}
