"""DSSE envelopes (https://github.com/secure-systems-lab/dsse) over in-toto statements, signed with ed25519.

Each zone (dirty observer, gate reviewer, clean runner) holds its own key; the audit log records the key id with
every signature, so a verifier can check who attested what. Keys are created on first use with mode 0600.
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

PAYLOAD_TYPE = "application/vnd.in-toto+json"


def pae(payload_type: str, payload: bytes) -> bytes:
    """DSSE pre-authentication encoding."""
    t = payload_type.encode()
    return b"DSSEv1 %d %s %d %s" % (len(t), t, len(payload), payload)


class Signer:
    def __init__(self, key_path: str | Path):
        self.key_path = Path(key_path)
        if self.key_path.exists():
            self._key = serialization.load_pem_private_key(self.key_path.read_bytes(), password=None)
        else:
            self.key_path.parent.mkdir(parents=True, exist_ok=True)
            self._key = Ed25519PrivateKey.generate()
            pem = self._key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption())
            fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(pem)
        self.public_pem = self._key.public_key().public_bytes(serialization.Encoding.PEM,
                                                              serialization.PublicFormat.SubjectPublicKeyInfo)
        self.keyid = hashlib.sha256(self.public_pem).hexdigest()[:16]

    def envelope(self, payload: bytes) -> dict:
        sig = self._key.sign(pae(PAYLOAD_TYPE, payload))
        return {"payloadType": PAYLOAD_TYPE, "payload": base64.b64encode(payload).decode(),
                "signatures": [{"keyid": self.keyid, "sig": base64.b64encode(sig).decode()}]}


def verify_envelope(envelope: dict, public_keys: dict[str, bytes]) -> bytes:
    """Return the payload if every signature verifies against a known key; raise otherwise."""
    payload = base64.b64decode(envelope["payload"])
    if not envelope.get("signatures"):
        raise ValueError("unsigned envelope")
    for s in envelope["signatures"]:
        pem = public_keys.get(s["keyid"])
        if pem is None:
            raise ValueError(f"unknown signing key {s['keyid']}")
        key = serialization.load_pem_public_key(pem)
        assert isinstance(key, Ed25519PublicKey)
        key.verify(base64.b64decode(s["sig"]), pae(envelope["payloadType"], payload))
    return payload
