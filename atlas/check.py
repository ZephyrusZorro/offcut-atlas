"""Validate an exported Offcut Atlas packet independently of the running workbench."""

import argparse
import hmac
import json
import sys
from pathlib import Path

from .proof import verify


def _unique_keys(pairs: list) -> dict:
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON object key {key!r}")
        obj[key] = value
    return obj


def _reject_constant(token: str) -> None:
    raise ValueError(f"invalid JSON number {token}")


def check_packet(packet: object, expected_digest: str | None = None) -> dict:
    """Return a machine-readable verdict. Never trust the recorded pass flag alone."""
    try:
        if not isinstance(packet, dict) or packet.get("format") != "offcut-atlas/1":
            raise ValueError("unsupported packet format")
        request = packet.get("request")
        claimed = packet.get("verification")
        if not isinstance(request, dict) or not isinstance(claimed, dict):
            raise ValueError("request and verification objects are required")
        if not isinstance(packet.get("run_id"), str) or not packet["run_id"].strip():
            raise ValueError("run_id is required")
        proof = verify(packet.get("stocks"), request.get("parts"), request.get("kerf_mm"),
                       request.get("reuse_mm"), packet.get("result"))
        if not proof["valid"]:
            return proof
        digest = claimed.get("digest")
        if (claimed.get("valid") is not True or not isinstance(digest, str)
                or not digest.isascii() or not hmac.compare_digest(proof["digest"], digest)):
            raise ValueError("recorded certificate differs from recomputed certificate")
        if expected_digest is not None:
            if not expected_digest.isascii() or not hmac.compare_digest(digest, expected_digest.lower()):
                raise ValueError("allocation differs from the supplied reference digest")
        return proof
    except ValueError as exc:
        return {"valid": False, "digest": "", "checks": [], "errors": [str(exc)]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path, help="path to a JSON run packet")
    parser.add_argument("--expect-digest", help="SHA-256 copied from a trusted reference")
    args = parser.parse_args(argv)
    try:
        with args.packet.open("r", encoding="utf-8-sig") as handle:
            packet = json.load(handle, object_pairs_hook=_unique_keys,
                               parse_constant=_reject_constant)
        verdict = check_packet(packet, args.expect_digest)
    except (OSError, ValueError, RecursionError) as exc:
        verdict = {"valid": False, "digest": "", "checks": [], "errors": [str(exc)]}
    print(json.dumps(verdict, indent=2))
    return 0 if verdict["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
