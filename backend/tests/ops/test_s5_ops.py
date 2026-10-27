from typing import Any

import pytest
import yaml

from tests.ops.repo import repo_path

AI_SECRETS = {"ai_api_key", "ai_ca_bundle"}
DOCS = {
    "docs/ops/ai-analiz.md": ("ai.enabled", "ai-enable", "compose.ai.yml", "Ключ API",
                              "EGRESS_PROXY", "90", "claude-opus-5-5", "ai.model",
                              "информационной безопасности", "/audit/ai-requests"),
    "docs/security/ai-data-flow.md": ("STRIDE", "14 000", "ai_context_rejected", "ФИО",
                                      "api.anthropic.com", "ai.enabled"),
}


def _load(path: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(repo_path(path).read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="module")
def prod() -> dict[str, Any]:
    return _load("deploy/compose.prod.yml")


@pytest.fixture(scope="module")
def overlay() -> dict[str, Any]:
    return _load("deploy/compose.ai.yml")


def test_prod_api_is_offline_without_overlay(prod: dict[str, Any]) -> None:
    api = prod["services"]["api"]
    assert "egress" not in api["networks"]
    for name, svc in prod["services"].items():
        assert not AI_SECRETS & set(svc.get("secrets", [])), name
        assert not any(k.startswith("AI_") for k in (svc.get("environment") or {})), name


def test_ai_overlay_extends_only_api(prod: dict[str, Any], overlay: dict[str, Any]) -> None:
    assert set(overlay["services"]) == {"api"}
    api = overlay["services"]["api"]
    assert set(api["networks"]) == {"backend", "web", "egress"}
    assert set(api["secrets"]) == set(prod["services"]["api"]["secrets"]) | {"ai_ca_bundle"}
    env = api["environment"]
    assert env["AI_PROVIDER"] == "anthropic"
    assert env["HTTPS_PROXY"] == "${EGRESS_PROXY:-}"
    assert env["AI_EGRESS"] == "1"  # Settings.problems(): proksisiz prod'da api ishga tushmaydi
    assert {"db", "redis", "localhost"} <= set(env["NO_PROXY"].split(","))
    # U6/U10: API kaliti Docker secret yoki env emas — faqat panel (integrations)
    assert "ai_api_key" not in api["secrets"] and "ai_api_key" not in overlay["secrets"]
    assert not any("KEY" in key for key in env)
    assert "ai_ca_bundle" in overlay["secrets"]


def test_dev_uses_fake_provider() -> None:
    dev = _load("deploy/compose.yml")
    assert dev["services"]["api"]["environment"]["AI_PROVIDER"] == "fake"
    assert not AI_SECRETS & set(dev["services"]["api"].get("secrets", []))


def test_caddy_streams_ai_without_compression() -> None:
    for path in ("deploy/caddy/Caddyfile.dev", "deploy/caddy/Caddyfile.prod"):
        content = repo_path(path).read_text(encoding="utf-8")
        assert "@compress not path /api/v1/ai/analyze" in content, path
        assert "encode @compress zstd gzip" in content, path
        assert "flush_interval -1" in content, path
        assert content.index("handle /api/v1/ai/analyze") < content.index("	handle /api/* {"), path


def test_docs_and_secrets() -> None:
    for path, needles in DOCS.items():
        content = repo_path(path).read_text(encoding="utf-8")
        for needle in needles:
            assert needle in content, (path, needle)
    hardening = repo_path("docs/ops/host-hardening.md").read_text(encoding="utf-8")
    assert "api.anthropic.com" in hardening and "compose.ai.yml" in hardening
    assert "DOCKER-USER" in hardening and "AI_EGRESS" in hardening
    readme = repo_path("deploy/secrets.example/README.md").read_text(encoding="utf-8")
    assert "ai_ca_bundle" in readme and "Docker secret EMAS" in readme
    script = repo_path("scripts/prod_config.sh").read_text(encoding="utf-8")
    assert "compose.ai.yml" in script and "ai_ca_bundle" in script
