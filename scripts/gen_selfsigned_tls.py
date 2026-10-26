"""Sinov va selftest uchun o'z-o'zidan imzolangan TLS sertifikat (ECDSA P-256).
PROD'DA ISHLATILMAYDI — prod'da korporativ sertifikat (docs/ops/install-upgrade.md).

    python scripts/gen_selfsigned_tls.py --out DIR --name ugk.test \
        [--cert-file tls_cert] [--key-file tls_key] [--days 30] [--mode 0600]
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def build(name: str, days: int) -> tuple[bytes, bytes]:
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return cert.public_bytes(serialization.Encoding.PEM), key_pem


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gen_selfsigned_tls")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--cert-file", default="tls_cert")
    parser.add_argument("--key-file", default="tls_key")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--mode", default="0600")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    cert, key = build(args.name, args.days)
    for filename, data in ((args.cert_file, cert), (args.key_file, key)):
        path = args.out / filename
        path.write_bytes(data)
        os.chmod(path, int(args.mode, 8))
    sys.stdout.write(f"Sinov sertifikati: {args.out / args.cert_file} ({args.name}, {args.days} kun)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
