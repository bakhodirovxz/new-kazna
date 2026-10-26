from typing import Any

import yaml

from tests.ops.repo import repo_path

TARGETS = ["make check", "make e2e-ci", "make scan"]


def _load(relative: str) -> Any:
    return yaml.safe_load(repo_path(relative).read_text(encoding="utf-8"))


def _github_runs(workflow: dict[str, Any]) -> list[str]:
    return [
        step["run"].strip()
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if "run" in step
    ]


def test_github_runs_same_make_targets() -> None:
    assert _github_runs(_load(".github/workflows/ci.yml")) == TARGETS


def test_gitlab_runs_same_make_targets() -> None:
    ci = _load(".gitlab-ci.yml")
    scripts = [
        line.strip()
        for job in ci.values()
        if isinstance(job, dict) and "script" in job
        for line in job["script"]
    ]
    assert scripts == TARGETS


def test_full_history_for_gitleaks() -> None:
    workflow = _load(".github/workflows/ci.yml")
    for job in workflow["jobs"].values():
        checkout = next(
            s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")
        )
        assert checkout["with"]["fetch-depth"] == 0
    assert _load(".gitlab-ci.yml")["variables"]["GIT_DEPTH"] == "0"


def test_github_token_is_read_only() -> None:
    workflow = _load(".github/workflows/ci.yml")
    assert workflow["permissions"] == {"contents": "read"}
    triggers = workflow.get("on", workflow.get(True))  # YAML 1.1: `on` → True
    assert {"push", "pull_request", "schedule"} <= set(triggers)
