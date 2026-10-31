"""One canonical JSON form, shared by proposals, approvals, the gateway and the ledger.

Sorted keys, no whitespace, UTF-8, no floats (callers use ints and ISO strings).
"""
from __future__ import annotations

import hashlib
import json


def canonical(obj) -> str:
    def check(o):
        if isinstance(o, float):
            raise ValueError("floats are not allowed in canonical payloads")
        if isinstance(o, dict):
            for v in o.values():
                check(v)
        elif isinstance(o, list):
            for v in o:
                check(v)
    check(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def payload_hash(obj) -> str:
    return sha256_hex(canonical(obj))
