"""
Skill Examples - High-level helper functions for skill operations.
"""

from __future__ import annotations

import io
import os
import time
import zipfile
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    import anthropic

_KEEP = os.getenv("OMA_KEEP_RESOURCES", "0") == "1"

# Manually uploaded custom skills used by the live multi-skill e2e case.
UPLOADED_SKILL_TITLES = (
    "find-skills",
    "baoyu-slide-deck",
    "baoyu-infographic",
)

_MULTI_SKILL_PROMPT = (
    "You have three custom skills mounted: find-skills, "
    "baoyu-slide-deck, and baoyu-infographic.\n"
    "Do NOT generate images, slide decks, or run external CLIs.\n"
    "Reply in plain text only. Confirm all three skills are available "
    "by listing each name on its own line with one short sentence about "
    "what it does. End with the exact marker: SKILLS_OK."
)


class SkillExamples:
    """Example operations for skills."""

    @staticmethod
    def make_skill_zip(name: str = "sdk-e2e-skill") -> bytes:
        """
        Create a skill zip file for testing.
        
        Args:
            name: Name for the skill
            
        Returns:
            Bytes of the zip file
        """
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "SKILL.md",
                f"---\nname: {name}\ndescription: SDK e2e validation skill. Safe to delete.\n---\n\n# {name}\n",
            )
        return buf.getvalue()

    @staticmethod
    def list_skills(client: anthropic.Anthropic) -> list:
        """
        List all skills.
        
        Args:
            client: Anthropic client instance
            
        Returns:
            List of skills
        """
        page = client.beta.skills.list()
        skills = list(page)
        assert isinstance(skills, list)
        assert len(skills) >= 1  # at least built-in skills exist
        return skills

    @staticmethod
    def _skill_title(skill: Any) -> str:
        return str(
            getattr(skill, "display_title", None)
            or getattr(skill, "name", None)
            or ""
        ).strip()

    @staticmethod
    def _skill_version(skill: Any) -> str:
        version = (
            getattr(skill, "latest_version", None)
            or getattr(skill, "version", None)
            or ""
        )
        return str(version)

    @staticmethod
    def resolve_skills_by_title(
        client: anthropic.Anthropic,
        titles: tuple[str, ...] | list[str] = UPLOADED_SKILL_TITLES,
    ) -> dict[str, Any]:
        """
        Resolve uploaded skills by display_title / name.

        Returns:
            Mapping of title -> skill object for each requested title.
        """
        wanted = {title: None for title in titles}
        for skill in SkillExamples.list_skills(client):
            title = SkillExamples._skill_title(skill)
            if title in wanted and wanted[title] is None:
                wanted[title] = skill

        missing = [title for title, skill in wanted.items() if skill is None]
        assert not missing, (
            f"missing uploaded skills {missing}; "
            f"upload them in Console /skills first"
        )
        return wanted  # type: ignore[return-value]

    @staticmethod
    def _wait_session_idle(
        client: anthropic.Anthropic,
        session_id: str,
        *,
        timeout_sec: float = 180.0,
        poll_sec: float = 1.0,
    ) -> Any:
        deadline = time.time() + timeout_sec
        last = None
        while time.time() < deadline:
            last = client.beta.sessions.retrieve(session_id)
            status = getattr(last, "status", None)
            if status == "idle":
                return last
            if status == "failed":
                raise RuntimeError(f"session {session_id} failed")
            time.sleep(poll_sec)
        raise TimeoutError(
            f"session {session_id} not idle within {timeout_sec}s "
            f"(last_status={getattr(last, 'status', None)})"
        )

    @staticmethod
    def _collect_agent_text(client: anthropic.Anthropic, session_id: str) -> str:
        """Collect agent.message text via raw events API (wire-normalized)."""
        resp = client.get(
            f"/v1/sessions/{session_id}/events?order=asc&limit=500",
            cast_to=httpx.Response,
        )
        parts: list[str] = []
        for item in resp.json().get("data", []):
            event = item.get("data") if isinstance(item.get("data"), dict) else item
            if not isinstance(event, dict) or event.get("type") != "agent.message":
                continue
            for block in event.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text")
                    if text:
                        parts.append(str(text))
        # Streamed deltas are separate text blocks; join without separators.
        return "".join(parts)

    @staticmethod
    def use_uploaded_multi_skills(
        client: anthropic.Anthropic,
        *,
        titles: tuple[str, ...] = UPLOADED_SKILL_TITLES,
        model_id: str | None = None,
        timeout_sec: float = 180.0,
    ) -> dict:
        """
        Mount the three Console-uploaded skills on an agent and run one turn.

        Expects find-skills / baoyu-slide-deck / baoyu-infographic to already
        exist under /v1/skills (uploaded via Console). Asks the model only to
        confirm the skills are present — no image generation.
        """
        from .sessions import SessionExamples

        resolved = SkillExamples.resolve_skills_by_title(client, titles)
        skill_specs = [
            {
                "type": "custom",
                "skill_id": resolved[title].id,
                "version": SkillExamples._skill_version(resolved[title]),
            }
            for title in titles
        ]
        for spec in skill_specs:
            assert spec["skill_id"], spec
            assert spec["version"], spec

        model = {"id": model_id or os.getenv("OMA_MODEL", "qwen3.7-plus")}
        agent = client.beta.agents.create(
            name="sdk-e2e-multi-skills",
            model=model,
            system=(
                "You are an SDK e2e agent. Use only the mounted custom skills "
                "listed in your skill set. Prefer short factual replies."
            ),
            skills=skill_specs,
        )
        env = client.beta.environments.create(name="sdk-e2e-multi-skills-env")
        session = None
        try:
            retrieved = client.beta.agents.retrieve(agent.id)
            mounted_ids = {
                getattr(item, "skill_id", None)
                if not isinstance(item, dict)
                else item.get("skill_id")
                for item in (getattr(retrieved, "skills", None) or [])
            }
            for spec in skill_specs:
                assert spec["skill_id"] in mounted_ids, (
                    f"agent missing skill {spec['skill_id']}; "
                    f"mounted={mounted_ids}"
                )

            session = SessionExamples._create_session(
                client,
                agent.id,
                env.id,
                title="sdk-e2e-multi-skills",
            )
            client.beta.sessions.events.send(
                session.id,
                events=[
                    {
                        "type": "user.message",
                        "content": [
                            {"type": "text", "text": _MULTI_SKILL_PROMPT},
                        ],
                    },
                ],
            )
            SkillExamples._wait_session_idle(
                client,
                session.id,
                timeout_sec=timeout_sec,
            )
            reply = SkillExamples._collect_agent_text(client, session.id)
            # Normalize whitespace so streamed line-breaks inside tokens still match.
            compact = "".join(reply.lower().split())
            for title in titles:
                needle = "".join(title.lower().split())
                assert needle in compact, (
                    f"agent reply missing skill name {title!r}: {reply[:800]}"
                )
            assert "SKILLS_OK" in "".join(reply.split()), (
                f"agent reply missing SKILLS_OK marker: {reply[:800]}"
            )
            return {
                "skills": {
                    title: {
                        "id": resolved[title].id,
                        "version": SkillExamples._skill_version(
                            resolved[title],
                        ),
                    }
                    for title in titles
                },
                "agent": agent,
                "session": session,
                "environment_id": env.id,
                "reply": reply,
            }
        finally:
            if _KEEP:
                print(
                    f"\n[KEEP] multi-skills agent={agent.id} "
                    f"session={getattr(session, 'id', None)} "
                    f"env={env.id}"
                )
            else:
                if session is not None:
                    try:
                        client.beta.sessions.archive(session.id)
                    except Exception:
                        pass
                try:
                    client.beta.agents.archive(agent.id)
                except Exception:
                    pass
                try:
                    client.beta.environments.archive(env.id)
                except Exception:
                    pass

    @staticmethod
    def retrieve_builtin_skill(client: anthropic.Anthropic, skill_id: str = "builtin_xlsx") -> dict:
        """
        Retrieve a built-in skill by ID.
        
        Args:
            client: Anthropic client instance
            skill_id: ID of the built-in skill to retrieve
            
        Returns:
            Dictionary with skill details
        """
        skill = client.beta.skills.retrieve(skill_id)
        assert skill.id == skill_id
        return {"skill": skill}

    @staticmethod
    def download_version(
        client: anthropic.Anthropic,
        name: str = "sdk-e2e-skill-dl",
    ) -> dict:
        """Upload a skill and download its version as a zip archive."""
        zip_bytes = SkillExamples.make_skill_zip(name)
        resp = client.post(
            "/v1/skills/upload",
            cast_to=httpx.Response,
            files={"file": (f"{name}.zip", zip_bytes, "application/zip")},
            options={"headers": {
                "Content-Type": "multipart/form-data",
                "X-Display-Title": name,
            }},
        )
        assert resp.status_code in (200, 201), resp.text
        skill_id = resp.json()["id"]
        try:
            versions = list(client.beta.skills.versions.list(skill_id))
            assert len(versions) >= 1
            version_id = versions[0].version
            downloaded = client.beta.skills.versions.download(
                version_id, skill_id=skill_id,
            )
            content = downloaded.read()
            assert len(content) > 0
            assert content[:2] == b"PK"
            return {
                "skill_id": skill_id,
                "version": version_id,
                "bytes": len(content),
            }
        finally:
            if not _KEEP:
                client.beta.skills.delete(skill_id)

    @staticmethod
    def upload_and_delete_skill(
        client: anthropic.Anthropic,
        name: str = "sdk-e2e-skill"
    ) -> dict:
        """
        Upload a skill, retrieve it, list its versions, then delete it.
        
        Args:
            client: Anthropic client instance
            name: Name for the skill
            
        Returns:
            Dictionary with skill details
        """
        zip_bytes = SkillExamples.make_skill_zip()
        resp = client.post(
            "/v1/skills/upload",
            cast_to=httpx.Response,
            files={"file": (f"{name}.zip", zip_bytes, "application/zip")},
            options={"headers": {
                "Content-Type": "multipart/form-data",
                "X-Display-Title": name,
            }},
        )
        assert resp.status_code in (200, 201), resp.text
        skill_id = resp.json()["id"]
        try:
            retrieved = client.beta.skills.retrieve(skill_id)
            assert retrieved.id == skill_id

            versions_page = client.beta.skills.versions.list(skill_id)
            assert isinstance(list(versions_page), list)
            return {"skill": retrieved, "versions": list(versions_page), "skill_id": skill_id}
        finally:
            if not _KEEP:
                client.beta.skills.delete(skill_id)
            else:
                print(f"\n[KEEP] skill {skill_id} ({name}) left — delete manually when done")
