"""Regression check for the RAG pipeline's answer quality.

Run this after any change to app/rag/pipeline.py, the system prompt, or the
retrieval/pinning logic. It asks a handful of real questions against the
live knowledge base and checks each answer for facts it MUST contain and
claims it MUST NOT make. It exists because the bug this session spent the
most time on -- an enumeration question about "SAWO Tower heaters" silently
answering about only 2 of 7 product families and citing the wrong source
page -- was only caught by a person reading the chat output. This script
would have caught it in under a minute.

Usage (from backend/, with the venv active):
    python -m scripts.rag_smoke_test

Exits 0 if every case passes, 1 otherwise -- safe to wire into a pre-deploy
check later if this project adds CI.

Calls answer_question() directly rather than going through the HTTP API, so
it needs no server running, and it deliberately does NOT trigger the
auto-promote-to-FAQ-draft background task (that only fires from the chat
router, not from answer_question() itself) -- so re-running this never
clutters the FAQ table with draft duplicates.

Each run does write real ChatLog rows (and, for a genuinely-unanswered case,
an UnansweredQuestion row) to whatever database DATABASE_URL points at, the
same as a real visitor asking the same question -- tagged with a
"regression-smoke-test" session_id so they're easy to spot or filter out in
the admin Logs view.
"""

import asyncio
import sys
import time
from dataclasses import dataclass, field

from app.db.session import AsyncSessionLocal
from app.rag.pipeline import RagResult, answer_question

SESSION_ID = "regression-smoke-test"

# An answer call taking longer than this fails the case outright -- the
# 377-second grounding-check-on-Vault-content bug found this session would
# have tripped this immediately instead of needing a manual latency probe.
MAX_SECONDS = 60.0


@dataclass
class Case:
    name: str
    question: str
    # Every one of these (case-insensitive) must appear somewhere in the answer.
    must_contain: list[str] = field(default_factory=list)
    # None of these may appear -- for known-wrong claims a past regression
    # actually made, so a repeat is caught immediately.
    must_not_contain: list[str] = field(default_factory=list)
    # If True, a fallback ("we've taken note...") response fails the case.
    expect_answered: bool = True


CASES: list[Case] = [
    Case(
        name="Tower enumeration — the original regression",
        question="do you have specs of sawo Tower heaters can you list them all and tell me where are they",
        # The actual defect in the original bug was incompleteness *within*
        # Tower (missing the Wall family entirely) plus the wrong citation --
        # not a failure to also name unrelated sibling brands (Aries, Cubos,
        # ...) that happen to share the same overview page. An earlier
        # version of this case required those names too and failed a
        # genuinely correct, complete answer that reasonably scoped itself
        # to "Tower heaters" as asked. Checking for all three Tower shapes
        # instead targets the real regression without over-fitting to one
        # particular good answer's phrasing.
        must_contain=["tower series", "round", "wall", "corner"],
        # The exact wrong citation from the original bug report: an
        # unrelated series named as "where to find" a Tower product.
        must_not_contain=["dragonfire series page"],
    ),
    Case(
        name="Single-fact lookup stays narrow",
        question="what kW is the SW3-45NS",
        must_contain=["4.5"],
    ),
    Case(
        name="Generic 'where do I find specs' doesn't invent a specific page",
        question="Where can I find detailed specs on our products?",
        must_contain=[],
        # The literal old FAQ #3/#5 wording this session found and rewrote —
        # a regression here means someone reintroduced the single-example
        # phrasing that let one series stand in for "the" answer.
        must_not_contain=["for example, on the dragonfire series page"],
    ),
    Case(
        name="Enumeration for a family with no hub page (Aries)",
        question="list all aries heaters",
        must_contain=["aries"],
    ),
]


async def run_case(db, case: Case) -> tuple[bool, str]:
    start = time.time()
    result: RagResult = await answer_question(db, case.question, session_id=SESSION_ID)
    elapsed = time.time() - start
    answer_lower = result.answer.lower()

    problems: list[str] = []
    if elapsed > MAX_SECONDS:
        problems.append(f"took {elapsed:.1f}s (limit {MAX_SECONDS:.0f}s)")
    if case.expect_answered and result.is_fallback:
        problems.append("got a fallback/unanswered response")
    for phrase in case.must_contain:
        if phrase.lower() not in answer_lower:
            problems.append(f"missing required phrase: {phrase!r}")
    for phrase in case.must_not_contain:
        if phrase.lower() in answer_lower:
            problems.append(f"contains forbidden phrase: {phrase!r}")

    ok = not problems
    detail = f"({elapsed:.1f}s)" if ok else "; ".join(problems)
    return ok, detail


async def main() -> int:
    failures = 0
    async with AsyncSessionLocal() as db:
        for case in CASES:
            ok, detail = await run_case(db, case)
            # A live third-party LLM call can hiccup on its own (a slow
            # provider, a dropped connection) independent of anything this
            # script is checking -- one retry filters that noise out without
            # hiding a real regression, which will fail the same way twice.
            if not ok:
                retry_ok, retry_detail = await run_case(db, case)
                if retry_ok:
                    ok, detail = retry_ok, f"passed on retry, first attempt: {detail}"
                else:
                    detail = f"{detail} [confirmed on retry: {retry_detail}]"
            status = "PASS" if ok else "FAIL"
            print(f"[{status}] {case.name} -- {detail}")
            if not ok:
                failures += 1

    print()
    if failures:
        print(f"{failures}/{len(CASES)} case(s) failed.")
        return 1
    print(f"All {len(CASES)} case(s) passed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
