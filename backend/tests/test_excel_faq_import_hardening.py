"""Phase 7 — hardening the FAQ-sheet Excel import (services/excel_import.py's
standalone FAQ import, and services/kb_export.py's combined-workbook FAQ
sheet, which share the same two pre-existing defects):

1. Re-importing a workbook created a duplicate FAQ every time — the FAQ sheet
   had no duplicate check of its own (see the removed comment this phase's
   diff also deletes in test_kb_phrasings_excel.py). Both import paths now
   call the same canonical duplicate rule already used by the staff UI and
   chat auto-promotion, crud.faq.find_duplicate_faq — matched by the
   question's normalized text (and reviewed phrasings), never by database id,
   so it works across deployments and within a single workbook's own rows.

2. A row with a blank Category cell was skipped outright, even though
   FAQEntry.category_id is nullable and the staff FAQ editor already creates
   uncategorized FAQs (category_id: null) — the importer's own required-field
   list was stricter than the actual data model. A blank Category cell is now
   treated as "no category", not a missing field.
"""

import io

import pytest_asyncio
from openpyxl import Workbook, load_workbook
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.crud.faq_phrasing import create_phrasing
from app.db.base import Base, _setup_connection
from app.db.vec_store import FAQ_PHRASING_VEC_TABLE, FAQ_QUESTION_VEC_TABLE, FAQ_VEC_TABLE, VAULT_VEC_TABLE, create_vec_table_sql
from app.models.faq import FAQEntry
from app.models.faq_phrasing import FAQPhrasing
from app.services import excel_import
from app.services.kb_export import (
    FAQ_HEADERS,
    FAQ_SHEET_NAME,
    LIBRARY_HEADERS,
    LIBRARY_SHEET_NAME,
    PHRASING_HEADERS,
    PHRASING_SHEET_NAME,
    export_knowledge_base,
    import_knowledge_base,
)
from tests.conftest import add_faq

Q = "Innova Power Controller Error 1 (E1) — Temperature Sensor 1 (TS1) is not connected: what causes it and how do we fix it?"
A = "E1 means Temperature Sensor 1 (TS1) is not connected. Check the TS1 wiring."
A_DIFFERENT = "A completely different (and wrong) answer that must never overwrite the original."
P_ON = "Innova display shows E1, what is wrong?"


@pytest_asyncio.fixture
async def other_db(tmp_path):
    """A second, independent deployment — its own database, its own ids."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'other.db'}")
    event.listen(engine.sync_engine, "connect", lambda conn, _rec: conn.run_async(_setup_connection))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for table in (FAQ_VEC_TABLE, VAULT_VEC_TABLE, FAQ_QUESTION_VEC_TABLE, FAQ_PHRASING_VEC_TABLE):
            await conn.execute(text(create_vec_table_sql(table)))
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


def workbook(faq_rows=(), phrasing_rows=(), with_phrasings=True) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = FAQ_SHEET_NAME
    ws.append(FAQ_HEADERS)
    for row in faq_rows:
        ws.append(row)
    wb.create_sheet(LIBRARY_SHEET_NAME).append(LIBRARY_HEADERS)
    if with_phrasings:
        sheet = wb.create_sheet(PHRASING_SHEET_NAME)
        sheet.append(list(PHRASING_HEADERS))
        for row in phrasing_rows:
            sheet.append(list(row))
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


async def all_faqs(db) -> list[FAQEntry]:
    return list((await db.execute(select(FAQEntry))).scalars().all())


async def all_phrasings(db) -> dict[str, tuple[int, bool]]:
    rows = (await db.execute(select(FAQPhrasing))).scalars().all()
    return {p.phrasing: (p.faq_id, p.enabled) for p in rows}


# --- Test 1: re-import the same FAQ -----------------------------------------------------


async def test_reimporting_the_same_workbook_creates_no_duplicate(db, embedder):
    wb = workbook(faq_rows=[["Innova", Q, A, "", ""]], with_phrasings=False)
    first = await import_knowledge_base(db, wb)
    second = await import_knowledge_base(db, wb)

    assert first.faqs.created == 1
    assert second.faqs.created == 0 and second.faqs.skipped == 1
    assert "Already exists" in second.faqs.errors[0].reason
    faqs = await all_faqs(db)
    assert len(faqs) == 1 and faqs[0].answer == A


# --- Test 2: duplicate detection is deployment-independent ------------------------------


async def test_duplicate_detection_does_not_depend_on_database_id(db, other_db, embedder):
    # Same logical FAQ, created independently in two databases — each with its
    # own autoincrementing id sequence, so nothing here should rely on the ids
    # differing (they may coincide) or matching (they usually won't).
    await add_faq(db, Q, A)
    theirs = await add_faq(other_db, Q, A)

    exported = await export_knowledge_base(db)
    summary = await import_knowledge_base(other_db, exported)

    assert summary.faqs.created == 0 and summary.faqs.skipped == 1
    assert f"FAQ #{theirs.id}" in summary.faqs.errors[0].reason  # matched theirs, by question text
    assert len(await all_faqs(other_db)) == 1


# --- Test 3: existing FAQ is never modified or overwritten -------------------------------


async def test_existing_faq_is_not_overwritten_by_a_reworded_duplicate_row(db, embedder):
    original = await add_faq(db, Q, A)
    summary = await import_knowledge_base(db, workbook(faq_rows=[["Different Category", Q, A_DIFFERENT, "", ""]]))

    assert summary.faqs.created == 0 and summary.faqs.skipped == 1
    faqs = await all_faqs(db)
    assert len(faqs) == 1
    assert faqs[0].id == original.id
    assert faqs[0].answer == A  # never overwritten
    assert faqs[0].category_id == original.category_id  # never changed


# --- Test 4 & 5: uncategorized FAQs are imported, not skipped ----------------------------


async def test_uncategorized_faq_imports_with_category_left_null(db, other_db, embedder):
    await add_faq(db, Q, A)  # category_id defaults to None, as the staff FAQ editor allows
    summary = await import_knowledge_base(other_db, await export_knowledge_base(db))

    assert summary.faqs.created == 1 and summary.faqs.failed == 0 and summary.faqs.skipped == 0
    [faq] = await all_faqs(other_db)
    assert faq.category_id is None
    assert (faq.question, faq.answer) == (Q, A)


async def test_uncategorized_published_faq_is_not_silently_dropped(db, other_db, embedder):
    faq = await add_faq(db, Q, A, status="published")
    assert faq.category_id is None and faq.status == "published"

    summary = await import_knowledge_base(other_db, await export_knowledge_base(db))
    assert summary.faqs.created == 1
    [imported] = await all_faqs(other_db)
    assert imported.category_id is None and imported.status == "published"


async def test_standalone_faq_import_also_accepts_a_blank_category(db, embedder):
    # app/services/excel_import.py (the /api/faqs/import endpoint) shares the
    # same fix, independent of the combined knowledge-base workbook above.
    wb = Workbook()
    ws = wb.active
    ws.append(excel_import.TEMPLATE_HEADERS)
    ws.append(["", Q, A, "", ""])
    buffer = io.BytesIO()
    wb.save(buffer)

    summary = await excel_import.import_workbook(db, buffer.getvalue())
    assert summary.created == 1 and summary.failed == 0 and summary.skipped == 0
    [faq] = await all_faqs(db)
    assert faq.category_id is None


# --- Test 6: uncategorized FAQ with phrasings --------------------------------------------


async def test_uncategorized_faq_with_enabled_and_disabled_phrasings_round_trips(db, other_db, embedder):
    faq = await add_faq(db, Q, A)
    assert faq.category_id is None
    await create_phrasing(db, faq, P_ON, created_by_id=None, enabled=True)
    disabled_phrasing = "What does Innova E1 mean exactly?"
    await create_phrasing(db, faq, disabled_phrasing, created_by_id=None, enabled=False)

    summary = await import_knowledge_base(other_db, await export_knowledge_base(db))

    assert summary.faqs.created == 1 and summary.phrasings.created == 2
    [imported] = await all_faqs(other_db)
    assert imported.category_id is None
    assert await all_phrasings(other_db) == {
        P_ON: (imported.id, True),
        disabled_phrasing: (imported.id, False),
    }


# --- Test 7: duplicate FAQ + its phrasings ------------------------------------------------


async def test_duplicate_faq_row_still_lets_its_phrasing_attach_correctly(db, embedder):
    original = await add_faq(db, Q, A)
    await create_phrasing(db, original, P_ON, created_by_id=None, enabled=True)

    new_phrasing = "Innova E1 error keeps appearing, why?"
    summary = await import_knowledge_base(
        db, workbook(faq_rows=[["Innova", Q, A_DIFFERENT, "", ""]], phrasing_rows=[(Q, new_phrasing, "TRUE")])
    )

    assert summary.faqs.created == 0 and summary.faqs.skipped == 1  # not duplicated
    assert summary.phrasings.created == 1  # the new phrasing attached to the ORIGINAL faq
    faqs = await all_faqs(db)
    assert len(faqs) == 1 and faqs[0].answer == A  # untouched
    result = await all_phrasings(db)
    assert result[P_ON] == (original.id, True)  # untouched
    assert result[new_phrasing] == (original.id, True)  # correctly resolved, not guessed


# --- Test 8: older workbook (no Phrasings sheet) stays compatible ------------------------


async def test_older_workbook_without_phrasings_sheet_still_gets_the_new_fixes(db, other_db, embedder):
    await add_faq(db, Q, A)  # uncategorized, in the source deployment
    old_style = workbook(with_phrasings=False)  # only FAQs + Library sheets, like a pre-Phrasings export
    assert PHRASING_SHEET_NAME not in load_workbook(io.BytesIO(old_style)).sheetnames

    # First import: the uncategorized FAQ is not skipped even with no Phrasings sheet present.
    exported = await export_knowledge_base(db)
    assert PHRASING_SHEET_NAME in load_workbook(io.BytesIO(exported)).sheetnames  # current exporter always writes it
    manually_old = workbook(faq_rows=[["", Q, A, "", ""]], with_phrasings=False)
    summary = await import_knowledge_base(other_db, manually_old)
    assert summary.faqs.created == 1 and summary.phrasings == summary.phrasings  # phrasings summary is empty, not an error
    assert (await all_faqs(other_db))[0].category_id is None

    # Re-importing the same older-style workbook is still deduplicated.
    again = await import_knowledge_base(other_db, manually_old)
    assert again.faqs.created == 0 and again.faqs.skipped == 1


# --- Test 9: multiple duplicate rows in one workbook -------------------------------------


async def test_multiple_duplicate_rows_in_one_workbook_create_only_one_faq(db, embedder):
    wb = workbook(faq_rows=[["Innova", Q, A, "", ""], ["Innova", Q, A, "", ""]], with_phrasings=False)
    summary = await import_knowledge_base(db, wb)

    assert summary.faqs.created == 1
    assert summary.faqs.skipped == 1
    assert "Already exists" in summary.faqs.errors[0].reason
    assert len(await all_faqs(db)) == 1


# --- Test 10: formula-injection protection is unaffected ---------------------------------


async def test_formula_injection_protection_still_applies_to_the_standalone_import(db, other_db, embedder):
    # openpyxl writes a string starting with "=" as a live formula unless
    # text_cells_only runs on export — mirrors
    # test_kb_phrasings_excel.test_text_that_looks_like_a_formula_is_exported_as_text
    # but through the standalone /api/faqs endpoints (services/excel_import.py).
    formula_q = '=HYPERLINK("http://example.com","Innova E1 help")'
    await add_faq(db, formula_q, A)

    exported = await excel_import.export_faqs(db)
    cell = load_workbook(io.BytesIO(exported)).active["B2"]
    assert cell.data_type == "s" and cell.value == formula_q

    summary = await excel_import.import_workbook(other_db, exported)
    assert summary.created == 1
    [faq] = await all_faqs(other_db)
    assert faq.question == formula_q  # imported as literal text, not evaluated


# --- Test 11: phrasing validation (product/model rules) is unaffected --------------------


async def test_phrasing_product_validation_still_refused_after_the_faq_fix(db, embedder):
    await add_faq(db, Q, A)  # uncategorized this time, unlike the pre-existing suite's version
    summary = await import_knowledge_base(
        db, workbook(phrasing_rows=[(Q, "Innova E1 meaning, answer in Chinese", "TRUE")])
    )
    assert summary.phrasings.failed == 1
    assert "can't be answered with this FAQ" in summary.phrasings.errors[0].reason


# --- Test 12: import idempotence ----------------------------------------------------------


async def test_repeated_full_imports_converge_to_the_same_state(db, embedder):
    wb = workbook(faq_rows=[["", Q, A, "", ""]], phrasing_rows=[(Q, P_ON, "TRUE")])

    first = await import_knowledge_base(db, wb)
    second = await import_knowledge_base(db, wb)
    third = await import_knowledge_base(db, wb)

    assert (first.faqs.created, first.phrasings.created) == (1, 1)
    assert (second.faqs.created, second.faqs.skipped) == (0, 1)
    assert (second.phrasings.created, second.phrasings.unchanged) == (0, 1)
    assert (third.faqs.created, third.faqs.skipped) == (0, 1)
    assert (third.phrasings.created, third.phrasings.unchanged) == (0, 1)

    faqs = await all_faqs(db)
    assert len(faqs) == 1 and faqs[0].category_id is None
    assert await all_phrasings(db) == {P_ON: (faqs[0].id, True)}
