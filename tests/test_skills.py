"""E2E tests for /v1/skills — list + upload + retrieve + delete + multi-skill use."""

from __future__ import annotations

import os

import anthropic
import pytest

from oma_sdk.examples.skills import UPLOADED_SKILL_TITLES
from oma_sdk.examples import SkillExamples

_RUN_LIVE_MULTI = os.getenv("OMA_RUN_LIVE_MULTI_SKILLS", "0") == "1"


def test_skills_list(client: anthropic.Anthropic):
    skills = SkillExamples.list_skills(client)
    assert isinstance(skills, list)
    assert len(skills) >= 1  # at least built-in skills exist


def test_skills_retrieve_builtin(client: anthropic.Anthropic):
    result = SkillExamples.retrieve_builtin_skill(client)
    assert result["skill"].id == "builtin_xlsx"


def test_skills_upload_and_delete(client: anthropic.Anthropic):
    result = SkillExamples.upload_and_delete_skill(client)
    assert result["skill"].id == result["skill_id"]
    assert isinstance(result["versions"], list)


def test_skills_version_download(client: anthropic.Anthropic):
    result = SkillExamples.download_version(client)
    assert result["bytes"] > 0


def test_skills_resolve_uploaded_three(client: anthropic.Anthropic):
    """Console-uploaded find-skills / baoyu-slide-deck / baoyu-infographic exist."""
    resolved = SkillExamples.resolve_skills_by_title(client)
    assert set(resolved) == set(UPLOADED_SKILL_TITLES)
    for title in UPLOADED_SKILL_TITLES:
        assert resolved[title].id.startswith("skill_")
        assert SkillExamples._skill_version(resolved[title])


@pytest.mark.live
@pytest.mark.skipif(
    not _RUN_LIVE_MULTI,
    reason="set OMA_RUN_LIVE_MULTI_SKILLS=1 to run live multi-skill turn",
)
def test_skills_use_uploaded_three_live(client: anthropic.Anthropic):
    """
    Mount the three uploaded skills on an agent and run one confirmation turn.

      OMA_API_KEY=... OMA_BASE_URL=http://127.0.0.1:8787 \\
        pytest tests/test_skills.py::test_skills_use_uploaded_three_live -v -s
    """
    result = SkillExamples.use_uploaded_multi_skills(client)
    assert set(result["skills"]) == set(UPLOADED_SKILL_TITLES)
    assert result["agent"].id
    assert result["session"].id
    assert "SKILLS_OK" in result["reply"]
