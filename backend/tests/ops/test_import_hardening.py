"""Import himoyasi (review M1/I5): defusedxml prod image'da va Caddy yuklash timeout'lari."""

from __future__ import annotations

import pytest

from tests.ops.repo import repo_path


def test_prod_requirements_pin_defusedxml_with_hashes() -> None:
    text = repo_path("backend/requirements.txt").read_text(encoding="utf-8")
    block = text.split("\ndefusedxml==", 1)[1].split("\n    # via", 1)[0]
    assert "--hash=sha256:" in block
    assert "defusedxml" in repo_path("backend/requirements.in").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["Caddyfile.prod", "Caddyfile.dev"])
def test_caddy_limits_slow_uploads(name: str) -> None:
    text = repo_path(f"deploy/caddy/{name}").read_text(encoding="utf-8")
    assert "timeouts {" in text and "read_header 10s" in text and "read_body 30s" in text
