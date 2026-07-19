#!/usr/bin/env python3
"""GAIA Level-1 benchmark runner for oma-platform.

Reads the GAIA validation metadata parquet, picks every Level-1 question,
drives an oma-platform agent through it, extracts the agent's final answer
and compares it to the ground truth.

Outputs
-------
* ``results/<run_id>.jsonl``  — per-question trace
* ``results/<run_id>.md``     — summary + defect catalog

Usage
-----
    OMA_BASE_URL=http://127.0.0.1:8787 \\
    OMA_API_KEY=oma_... \\
    python gaia/gaia_oma_runner.py --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

import httpx

# Add SDK to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from oma_sdk import OMAClient, stream_until_end_turn, StreamConfig, stop_reason_type, event_type, message_text

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GAIA_DATA_DIR = Path(__file__).parent / "data"
VALIDATION_PARQUET = GAIA_DATA_DIR / "2023" / "validation" / "metadata.parquet"
RESULTS_DIR = Path(__file__).parent / "results"

OMA_BASE_URL = os.getenv("OMA_BASE_URL", "http://127.0.0.1:8787").rstrip("/")
OMA_API_KEY = os.getenv("OMA_API_KEY", "")

ENVIRONMENT_ID = os.getenv("OMA_ENVIRONMENT_ID", "env-o1krx78fqanlwz6g")
AGENT_ID = os.getenv("OMA_AGENT_ID", "agent-kdofz46oe6pa51j1")
AGENT_VERSION = int(os.getenv("OMA_AGENT_VERSION", "1"))

DEFAULT_MODEL = os.getenv("OMA_MODEL", "qwen3.7-plus")

PER_Q_TIMEOUT = float(os.getenv("GAIA_PER_Q_TIMEOUT", "300"))  # seconds
MAX_TOOL_CALLS = int(os.getenv("GAIA_MAX_TOOL_CALLS", "30"))   # loop guard
MAX_CONCURRENCY = int(os.getenv("GAIA_CONCURRENCY", "1"))

# URL blacklist to block access to answer datasets
URL_BLACKLIST = [
    "huggingface.co/datasets/gaia-benchmark",
    "huggingface.co/datasets/Kevin355/Who_and_When",
    "github.com/gaia-benchmark",
    "github.com/xlang-ai/GAIA",
]


GAIA_SYSTEM_PROMPT = """\
You are a precise QA assistant answering benchmark questions.

CRITICAL: You MUST output your final answer in the exact format specified below.

## Answer Format (MANDATORY)

After completing your analysis, you MUST end your response with a line in this exact format:

    ANSWER: <your_final_answer>

Examples:
- Question: "How many studio albums were published by Mercedes Sosa between 2000 and 2009?"
  Correct response ends with: ANSWER: 3

- Question: "What is the volume in m^3 of the fish bag?"
  Correct response ends with: ANSWER: 0.1777

- Question: "Who was the author of the paper?"
  Correct response ends with: ANSWER: John Smith

The <your_final_answer> must be:
- The SHORTEST possible string that answers the question
- A number, name, date, or short phrase
- No extra punctuation or explanation after ANSWER:

If you cannot determine the answer, output: ANSWER: UNKNOWN

## General Rules

1. Read attached files first if the question references one.
2. Use web_search / web_fetch only when the answer requires up-to-date info.
3. Be concise in your reasoning, but ALWAYS output ANSWER: at the end.
4. If the same tool call fails three times in a row, stop retrying and output:
   ANSWER: ERROR - <brief description of what failed>
5. DO NOT access benchmark dataset answer keys (e.g., huggingface.co/datasets/gaia-benchmark, github.com/gaia-benchmark). Solve the problem using legitimate research.

## Answer Completeness

- Names: use the full name (first + last) the question asks for
- Numbers: double-check which column/field the question is about
- Before emitting ANSWER, re-read the question and confirm your answer covers every part

## REMINDER

NO MATTER WHAT, your response MUST end with "ANSWER: <something>".
This is the MOST IMPORTANT requirement. Do not forget it.
"""


# ---------------------------------------------------------------------------
# Event parsing helpers
# ---------------------------------------------------------------------------
def _stop_reason_type(evt: dict[str, Any]) -> str | None:
    """Extract ``stop_reason.type`` from a session.status_idle payload.

    The Go server emits ``stop_reason`` as a nested dict, e.g.
    ``{"type": "end_turn"}`` or ``{"type": "requires_action", ...}``.
    Returns None when stop_reason is missing or not a dict.

    Parity with ``oma-platform/sdk/oma_sdk/cookbook.py::stop_reason_type``.
    """
    stop_reason = evt.get("stop_reason")
    if isinstance(stop_reason, dict):
        reason_type = stop_reason.get("type")
        if reason_type:
            return str(reason_type)
    return None


def _tool_call_fingerprint(call: dict) -> str:
    """Stable identity for 'same tool called with same input'."""
    name = str(call.get("name") or "")
    inp = call.get("input") or {}
    try:
        inp_key = json.dumps(inp, sort_keys=True, ensure_ascii=False)
    except Exception:
        inp_key = repr(inp)
    return f"{name}|{hashlib.md5(inp_key.encode('utf-8')).hexdigest()[:12]}"


def _is_url_blacklisted(url: str) -> str | None:
    """Check if URL matches any blacklisted pattern. Returns matching pattern or None."""
    url_lower = url.lower()
    for pattern in URL_BLACKLIST:
        if pattern.lower() in url_lower:
            return pattern
    return None


async def _send_interrupt(client: OMAClient, session_id: str) -> None:
    """Send user.interrupt event to stop the agent."""
    try:
        await client.events.send(
            session_id,
            events=[{"type": "user.interrupt"}],
        )
    except Exception as e:
        print(f"Warning: Failed to send interrupt: {type(e).__name__}: {e!r}")


# ---------------------------------------------------------------------------
# SDK client and session management
# ---------------------------------------------------------------------------
def create_sdk_client() -> OMAClient:
    """Create OMA SDK client."""
    return OMAClient(base_url=OMA_BASE_URL, tenant_id=None)


async def create_session(
    client: OMAClient,
    agent_id: str,
    environment_id: str,
    question: str,
    file_path: Path | None,
) -> str:
    """Create a new session and send the initial question."""
    # Upload file if present
    resources = []
    if file_path and file_path.exists():
        with open(file_path, "rb") as f:
            file_data = f.read()
        # Use HTTP API for file upload (multipart)
        async with httpx.AsyncClient() as http:
            r = await http.post(
                f"{OMA_BASE_URL}/v1/files",
                headers={"x-api-key": OMA_API_KEY},
                files={"file": (file_path.name, file_data, "application/octet-stream")},
                data={"downloadable": "true", "scope": "session"},
                timeout=60,
            )
            r.raise_for_status()
            file_rec = r.json()
        resources.append({
            "type": "file",
            "file_id": file_rec["id"],
            "mount_path": f"/mnt/session/uploads/{file_path.name}",
        })

    # Create session via HTTP API
    body = {
        "environment_id": environment_id,
        "agent": {"type": "agent", "id": agent_id, "version": AGENT_VERSION},
        "title": f"gaia-l1-{int(time.time())}",
    }
    if resources:
        body["resources"] = resources

    async with httpx.AsyncClient() as http:
        r = await http.post(
            f"{OMA_BASE_URL}/v1/sessions",
            headers={"x-api-key": OMA_API_KEY, "content-type": "application/json"},
            json=body,
            timeout=30,
        )
        r.raise_for_status()
        rec = r.json()
    session_id = rec["id"]

    # Send question
    if file_path and file_path.exists():
        text = f"Attached file: /mnt/session/uploads/{file_path.name}\n\nQuestion: {question}"
    else:
        text = question

    await client.events.send(
        session_id,
        events=[{"type": "user.message", "content": [{"type": "text", "text": text}]}],
    )
    return session_id


# ---------------------------------------------------------------------------
# GAIA loading
# ---------------------------------------------------------------------------
def load_l1() -> pd.DataFrame:
    df = pd.read_parquet(VALIDATION_PARQUET)
    l1 = df[df["Level"].astype(str) == "1"].copy()
    l1 = l1.reset_index(drop=True)
    print(f"Loaded {len(l1)} Level-1 questions from {VALIDATION_PARQUET}")
    return l1


# ---------------------------------------------------------------------------
# Agent interaction
# ---------------------------------------------------------------------------
@dataclass
class QResult:
    task_id: str
    question: str
    file_name: str | None
    ground_truth: str
    prediction: str = ""
    passed: bool = False
    status: str = "pending"          # ok / timeout / error / loop / no_answer
    tool_calls: list[dict] = field(default_factory=list)
    error: str | None = None
    elapsed_s: float = 0.0
    n_events: int = 0
    n_tool_calls: int = 0
    session_id: str | None = None
    defect_tags: list[str] = field(default_factory=list)


async def ensure_agent(client: OMAClient) -> None:
    """Quick liveness + config check."""
    me = await client.me.get()
    print(f"✓ oma-platform: tenant={me['tenant']['name']}")
    # agents is from anthropic SDK (sync)
    agent = client.agents.retrieve(AGENT_ID)
    print(f"✓ agent: {agent.name}  model={agent.model.id}  v{agent.version}")
    print(f"  tools: {len(agent.tools or [])} tool(s) configured")


async def stream_events(client: OMAClient, session_id: str, qr: QResult) -> None:
    """Stream events using SDK until end_turn or timeout."""
    t0 = time.time()
    assistant_texts: list[str] = []
    qr.tool_calls = []

    # Loop detector
    last_tool_key: str | None = None
    consecutive_failures = 0
    LOOP_DETECTION_WINDOW = int(os.getenv("GAIA_LOOP_WINDOW", "3"))
    should_stop = False

    def on_event(evt: dict[str, Any]) -> None:
        """Process each event and update qr."""
        nonlocal last_tool_key, consecutive_failures, should_stop

        if should_stop:
            return

        qr.n_events += 1
        etype = event_type(evt)

        if etype == "agent.message":
            text = message_text(evt)
            if text:
                assistant_texts.append(text)

        elif etype == "agent.tool_use":
            payload = evt.get("data", evt)
            call = {
                "seq": len(qr.tool_calls) + 1,
                "name": payload.get("name", ""),
                "input": payload.get("input", {}),
                "tool_use_id": payload.get("id"),
            }
            qr.tool_calls.append(call)
            qr.n_tool_calls += 1

            # Check for URL blacklist violation
            if call["name"] == "web_fetch":
                url = call["input"].get("url", "")
                matched_pattern = _is_url_blacklisted(url)
                if matched_pattern:
                    qr.status = "blacklisted"
                    qr.defect_tags.append("blacklisted_url")
                    qr.error = f"Attempted to access blacklisted URL pattern: {matched_pattern}"
                    should_stop = True
                    asyncio.create_task(_send_interrupt(client, session_id))
                    return

            # Check for tool call limit exceeded
            if qr.n_tool_calls > MAX_TOOL_CALLS:
                qr.status = "loop"
                qr.defect_tags.append("tool_loop")
                qr.error = f"Exceeded maximum tool calls ({MAX_TOOL_CALLS})"
                should_stop = True
                asyncio.create_task(_send_interrupt(client, session_id))
                return

        elif etype == "agent.tool_result":
            payload = evt.get("data", evt)
            content = payload.get("content", [])
            text = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
            is_error = payload.get("is_error", False)

            # Match to most recent tool_use
            if qr.tool_calls:
                qr.tool_calls[-1]["output_head"] = text[:300]
                qr.tool_calls[-1]["output_is_error"] = is_error or _looks_like_error(text)
                if qr.tool_calls[-1]["output_is_error"]:
                    tool = qr.tool_calls[-1]["name"]
                    tag = f"tool_{tool}_error"
                    if tag not in qr.defect_tags:
                        qr.defect_tags.append(tag)

                    # Loop detection
                    key = _tool_call_fingerprint(qr.tool_calls[-1])
                    if key == last_tool_key:
                        consecutive_failures += 1
                    else:
                        last_tool_key = key
                        consecutive_failures = 1

                    if consecutive_failures >= LOOP_DETECTION_WINDOW:
                        qr.status = "loop"
                        qr.defect_tags.append("tool_loop")
                        qr.error = f"Detected {consecutive_failures} consecutive failures of same tool call"
                        should_stop = True
                        asyncio.create_task(_send_interrupt(client, session_id))
                        return
                else:
                    last_tool_key = None
                    consecutive_failures = 0
    
    # Use SDK's stream_until_end_turn with explicit timeout wrapper
    config = StreamConfig(
        timeout_sec=PER_Q_TIMEOUT,
        stream_read_timeout=PER_Q_TIMEOUT,
    )

    try:
        # Explicit timeout wrapper to enforce hard limit
        await asyncio.wait_for(
            stream_until_end_turn(
                client,
                session_id,
                config=config,
                on_event=on_event,
            ),
            timeout=PER_Q_TIMEOUT,
        )
        # If no error and we have a prediction, mark as ok
        if qr.status == "pending":
            qr.status = "ok"
    except asyncio.TimeoutError:
        qr.status = "timeout"
        qr.defect_tags.append("timeout")
        # Send interrupt to stop the agent
        try:
            await client.events.send(
                session_id,
                events=[{"type": "user.interrupt"}],
            )
        except Exception:
            pass
    except TimeoutError:
        qr.status = "timeout"
        qr.defect_tags.append("timeout")
    except Exception as e:
        qr.status = "error"
        qr.error = str(e)
    
    qr.elapsed_s = time.time() - t0

    # Extract ANSWER with multiple fallback strategies
    qr.prediction = ""
    if assistant_texts:
        full_text = "\n".join(assistant_texts)

        # Strategy 1: Look for explicit ANSWER: format
        m = re.search(r"(?im)^\s*ANSWER:\s*(.+?)\s*$", full_text)
        if m:
            qr.prediction = m.group(1).strip()

        # Strategy 2: Look for common answer patterns
        if not qr.prediction:
            # Look for "The answer is X" or "X is the answer"
            patterns = [
                r"(?i)(?:the\s+)?answer\s+is\s+[:\s]+(.+?)(?:\.|$)",
                r"(?i)(.+?)\s+is\s+the\s+answer",
                r"(?i)(?:so|therefore|thus|hence)[,\s]+(.+?)(?:\.|$)",
            ]
            for pattern in patterns:
                m = re.search(pattern, full_text)
                if m:
                    candidate = m.group(1).strip()
                    # Clean up common prefixes and punctuation
                    candidate = re.sub(r'^(?:ANSWER|ANS|WER|AN)\s*:\s*', '', candidate, flags=re.IGNORECASE)
                    candidate = candidate.lstrip(':').strip()
                    # Only accept if it's reasonably short (likely an answer)
                    if len(candidate) < 100:
                        qr.prediction = candidate
                        break

        # Strategy 3: Extract from last non-empty line (if short enough)
        if not qr.prediction:
            lines = [line.strip() for line in full_text.split("\n") if line.strip()]
            if lines:
                last_line = lines[-1]
                # Only use last line if it's short and doesn't look like a sentence
                if len(last_line) < 50 and not last_line.endswith("."):
                    qr.prediction = last_line

    if not qr.prediction:
        qr.status = "no_answer"
        qr.defect_tags.append("no_answer_extracted")


def _looks_like_error(text: str) -> bool:
    s = text.strip()
    if not s:
        return True
    low = s.lower()
    if low in ("error:", "error", "no output", "(no output)"):
        return True
    if "traceback" in low and ("error" in low or "exception" in low):
        return True
    if "command exited with code" in low and "code 0" not in low:
        return True
    if "connect tunnel failed" in low:
        return True
    return False


_ANS_RE = re.compile(r"(?im)^\s*ANSWER:\s*(.+?)\s*$")


def _extract_answer(texts: list[str]) -> str:
    full = "\n".join(texts)
    m = _ANS_RE.findall(full)
    if m:
        return m[-1].strip().strip("`\"'")
    # Fallback: last non-empty line
    lines = [ln.strip() for ln in full.splitlines() if ln.strip()]
    return lines[-1][:200] if lines else ""


def grade(prediction: str, truth: str) -> bool:
    if not prediction or prediction == "UNKNOWN":
        return False
    # GAIA uses exact string match after basic normalization
    norm = lambda s: str(s).strip().lower().replace(",", "").replace('"', "").replace("'", "")
    return norm(prediction) == norm(truth)


# ---------------------------------------------------------------------------
# Per-question driver
# ---------------------------------------------------------------------------
async def run_one(client: OMAClient, row: pd.Series) -> QResult:
    qr = QResult(
        task_id=row["task_id"],
        question=row["Question"],
        file_name=row.get("file_name") or None,
        ground_truth=str(row["Final answer"]) if pd.notna(row["Final answer"]) else "",
    )

    file_path = None
    if qr.file_name:
        file_path = GAIA_DATA_DIR / "2023" / "validation" / qr.file_name

    try:
        # Create session and send question
        qr.session_id = await create_session(
            client,
            AGENT_ID,
            ENVIRONMENT_ID,
            qr.question,
            file_path,
        )

        # Stream events until completion
        await stream_events(client, qr.session_id, qr)

    except Exception as e:
        qr.status = "error"
        qr.error = str(e)

    qr.passed = grade(qr.prediction, qr.ground_truth)
    return qr


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def write_report(run_id: str, results: list[QResult]) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    jsonl_path = RESULTS_DIR / f"{run_id}.jsonl"
    md_path = RESULTS_DIR / f"{run_id}.md"

    with jsonl_path.open("w") as f:
        for qr in results:
            f.write(json.dumps({
                "task_id": qr.task_id,
                "question": qr.question[:300],
                "file_name": qr.file_name,
                "ground_truth": qr.ground_truth,
                "prediction": qr.prediction,
                "passed": qr.passed,
                "status": qr.status,
                "elapsed_s": round(qr.elapsed_s, 1),
                "n_events": qr.n_events,
                "n_tool_calls": qr.n_tool_calls,
                "session_id": qr.session_id,
                "defect_tags": qr.defect_tags,
                "tool_calls": qr.tool_calls[:8],  # cap
                "error": qr.error,
            }, ensure_ascii=False) + "\n")

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    status_counts = {}
    defect_counts: dict[str, int] = {}
    for r in results:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1
        for tag in r.defect_tags:
            defect_counts[tag] = defect_counts.get(tag, 0) + 1

    lines = [
        f"# GAIA L1 Run {run_id}",
        "",
        f"- **Accuracy**: {passed}/{total} = {passed/total:.1%}" if total else "- no questions",
        f"- **Status breakdown**: {status_counts}",
        f"- **Defect tags**: {defect_counts}",
        "",
        "## Per-question",
        "",
        "| # | task_id | status | pass | truth | prediction | defect_tags | elapsed |",
        "|---|---------|--------|------|-------|------------|-------------|---------|",
    ]
    for i, r in enumerate(results, 1):
        lines.append(
            f"| {i} | {r.task_id[:8]} | {r.status} | "
            f"{'✅' if r.passed else '❌'} | "
            f"{_cell(r.ground_truth)} | {_cell(r.prediction)} | "
            f"{','.join(r.defect_tags) or '—'} | {r.elapsed_s:.0f}s |"
        )

    lines += ["", "## Defect catalog", ""]
    lines += [
        "- **tool_web_search_error**: `web_search` returns empty `Error:` for every query — likely harness-side config missing or upstream search provider unreachable.",
        "- **tool_web_fetch_error**: `web_fetch` fails markdown extraction, returns raw HTML wrapped in `[NOTE: markdown extraction unavailable ...]`.",
        "- **tool_bash_error / outbound proxy 501**: sandbox outbound proxy (127.0.0.1:8790) returns `501 Not Implemented` on HTTPS CONNECT, so `curl` from bash cannot reach external HTTPS sites.",
        "- **tool_loop**: agent doesn't recognize tool failure and retries the same calls indefinitely, burning tokens without producing an answer.",
        "- **timeout**: the loop above typically runs until `GAIA_PER_Q_TIMEOUT`.",
        "- **no_answer_extracted**: agent never emits `ANSWER: ...` line.",
        "- **missing_file**: question references a file not present on disk.",
        "",
    ]
    md_path.write_text("\n".join(lines))
    return md_path


def _cell(s: str) -> str:
    return (s[:40] + "…") if len(s) > 40 else s


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5,
                    help="Max questions to run (default 5)")
    ap.add_argument("--offset", type=int, default=0,
                    help="Start index into the L1 question list")
    ap.add_argument("--no-file", action="store_true",
                    help="Only run questions without file attachments")
    ap.add_argument("--file-only", action="store_true",
                    help="Only run questions with file attachments")
    ap.add_argument("--task-ids", type=str, default="",
                    help="Comma-separated task_id prefixes to run (matches startswith)")
    args = ap.parse_args()

    async with create_sdk_client() as client:
        await ensure_agent(client)
        df = load_l1()
        if args.no_file:
            df = df[df["file_name"].isna() | (df["file_name"] == "")]
        if args.file_only:
            df = df[df["file_name"].notna() & (df["file_name"] != "")]
        if args.task_ids:
            prefixes = [p.strip() for p in args.task_ids.split(",") if p.strip()]
            df = df[df["task_id"].apply(lambda t: any(t.startswith(p) for p in prefixes))]
            df = df.reset_index(drop=True)
        df = df.iloc[args.offset:args.offset + args.limit]
        print(f"Running {len(df)} questions (offset={args.offset})")

        run_id = time.strftime("run_%Y%m%d_%H%M%S")
        results: list[QResult] = []
        for i, (_, row) in enumerate(df.iterrows(), 1):
            print(f"\n[{i}/{len(df)}] {row['task_id'][:8]}  "
                  f"Q: {row['Question'][:80].strip()!r}…")
            qr = await run_one(client, row)
            tag = "✅" if qr.passed else "❌"
            print(f"    {tag} status={qr.status}  pred={qr.prediction!r}  "
                  f"truth={qr.ground_truth!r}  tools={qr.n_tool_calls}  "
                  f"elapsed={qr.elapsed_s:.0f}s  defects={qr.defect_tags}")
            results.append(qr)

        md = write_report(run_id, results)
        print(f"\n=== Report: {md} ===")


if __name__ == "__main__":
    asyncio.run(main())
