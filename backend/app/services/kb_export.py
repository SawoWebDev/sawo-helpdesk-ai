"""Combined FAQ + Library export/import: one workbook, so the whole knowledge
base can be backed up or moved to another deployment without recrawling
Library sources or re-entering FAQs by hand.

Sheets: FAQs, Library, and Phrasings (staff-reviewed alternate phrasings,
models/faq_phrasing.py). Every sheet is optional on import, so workbooks
exported before the Phrasings sheet existed import exactly as before.
"""

import io
from dataclasses import dataclass, field

from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.category import build_category_path_map, get_or_create_category_path
from app.crud.faq import create_faq, find_duplicate_faq, list_faqs_all
from app.crud.faq_phrasing import create_phrasing
from app.crud.vault import create_vault_entry, list_vault_entries_all
from app.models.faq import FAQEntry
from app.models.faq_phrasing import FAQPhrasing
from app.rag.question_normalize import normalize_question
from app.rag.reindex import embed_entry
from app.rag.vault_reindex import embed_vault_entry

FAQ_SHEET_NAME = "FAQs"
LIBRARY_SHEET_NAME = "Library"

FAQ_HEADERS = ["Category", "Question", "Answer", "Image URL", "Reference URL", "Status"]
FAQ_REQUIRED_HEADERS = ["Category", "Question", "Answer"]
FAQ_STATUSES = ("published", "draft")

LIBRARY_HEADERS = ["Category", "Title", "Content", "Tags", "Source URL", "Memory Enabled"]
LIBRARY_REQUIRED_HEADERS = ["Category", "Title", "Content"]

# A phrasing is tied to its FAQ by the FAQ's question text, not its id: ids
# differ between deployments, the question is what the FAQs sheet carries, and
# it resolves the same way the chat does (normalize_question).
PHRASING_SHEET_NAME = "Phrasings"
PHRASING_HEADERS = ["FAQ Question", "Phrasing", "Enabled"]
PHRASING_REQUIRED_HEADERS = ["FAQ Question", "Phrasing"]


def parse_faq_status(raw: str) -> str | None:
    """Normalizes a "Status" cell to "published"/"draft". Blank -> "published",
    so a file exported before this column existed (or a blank cell in a
    hand-edited one) still imports exactly as before. Returns None for a
    value that isn't one of the two recognized statuses, so the caller can
    report it as a row error instead of silently guessing."""
    value = raw.strip().lower()
    if not value:
        return "published"
    return value if value in FAQ_STATUSES else None


def text_cells_only(ws) -> None:
    """openpyxl stores any string that starts with "=" as a formula. Every
    exported cell is text taken from the database (an FAQ question can come
    from a public chat message via auto-promotion), so a value like
    '=HYPERLINK(...)' would run as a formula when the file is opened, and read
    back as empty on re-import. Such cells are written as plain text."""
    for row in ws.iter_rows():
        for cell in row:
            if cell.data_type == "f":
                cell.data_type = "s"


@dataclass
class RowError:
    row_number: int
    reason: str


@dataclass
class ImportSummary:
    created: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[RowError] = field(default_factory=list)
    unchanged: int = 0  # already present exactly as in the file (Phrasings only)


@dataclass
class KnowledgeBaseImportSummary:
    faqs: ImportSummary
    library: ImportSummary
    phrasings: ImportSummary = field(default_factory=ImportSummary)


async def export_knowledge_base(db: AsyncSession) -> bytes:
    """Same column layout each entity's own standalone export already uses
    (see services/excel_import.py), just as two sheets in one file."""
    faq_entries = await list_faqs_all(db)
    vault_entries = await list_vault_entries_all(db)
    category_paths = await build_category_path_map(db)

    wb = Workbook()
    faq_ws = wb.active
    faq_ws.title = FAQ_SHEET_NAME
    faq_ws.append(FAQ_HEADERS)
    for entry in faq_entries:
        category_path = category_paths.get(entry.category_id, "") if entry.category_id else ""
        faq_ws.append(
            [
                category_path,
                entry.question,
                entry.answer,
                (entry.image_urls or [""])[0],
                (entry.reference_urls or [""])[0],
                entry.status,
            ]
        )

    library_ws = wb.create_sheet(LIBRARY_SHEET_NAME)
    library_ws.append(LIBRARY_HEADERS)
    for entry in vault_entries:
        category_path = category_paths.get(entry.category_id, "") if entry.category_id else ""
        library_ws.append(
            [
                category_path,
                entry.title,
                entry.content,
                ", ".join(entry.tags or []),
                entry.source_url or "",
                "TRUE" if entry.memory_enabled else "FALSE",
            ]
        )

    phrasing_ws = wb.create_sheet(PHRASING_SHEET_NAME)
    phrasing_ws.append(PHRASING_HEADERS)
    phrasing_rows = await db.execute(
        select(FAQPhrasing, FAQEntry.question)
        .join(FAQEntry, FAQEntry.id == FAQPhrasing.faq_id)
        .order_by(FAQPhrasing.faq_id, FAQPhrasing.id)
    )
    for phrasing, faq_question in phrasing_rows.all():
        phrasing_ws.append([faq_question, phrasing.phrasing, "TRUE" if phrasing.enabled else "FALSE"])

    for ws in wb.worksheets:
        text_cells_only(ws)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _row_cells(headers: list[str], row: tuple) -> dict[str, str]:
    col_index = {h: i for i, h in enumerate(headers)}

    def cell(name: str) -> str:
        idx = col_index.get(name)
        if idx is None or idx >= len(row):
            return ""
        value = row[idx]
        return str(value).strip() if value is not None else ""

    return {name: cell(name) for name in headers}


async def _import_faq_sheet(db: AsyncSession, ws) -> ImportSummary:
    summary = ImportSummary()
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        return summary

    headers = [str(h).strip() if h is not None else "" for h in header_row]
    missing = [h for h in FAQ_REQUIRED_HEADERS if h not in headers]
    if missing:
        summary.failed += 1
        summary.errors.append(RowError(row_number=1, reason=f"Missing required column(s): {', '.join(missing)}"))
        return summary

    for row_number, row in enumerate(rows_iter, start=2):
        if row is None or all(cell is None for cell in row):
            continue
        cells = _row_cells(headers, row)
        category_path = cells.get("Category", "")
        question = cells.get("Question", "")
        answer = cells.get("Answer", "")
        image_url = cells.get("Image URL", "")
        reference_url = cells.get("Reference URL", "")
        status_raw = cells.get("Status", "")

        # Category is optional: FAQEntry.category_id is nullable and the staff
        # FAQ editor already creates FAQs with no category — a blank cell
        # means "no category", not an error.
        missing_fields = [
            name for name, value in [("Question", question), ("Answer", answer)] if not value
        ]
        if missing_fields:
            summary.skipped += 1
            summary.errors.append(
                RowError(row_number=row_number, reason=f"Missing required field(s): {', '.join(missing_fields)}")
            )
            continue

        # Status round-trips 1:1 with what was exported (blank -> published,
        # for files exported before this column existed) rather than always
        # publishing on import — a draft re-imported must come back a draft.
        status = parse_faq_status(status_raw)
        if status is None:
            summary.skipped += 1
            summary.errors.append(
                RowError(
                    row_number=row_number,
                    reason=f'Status must be "Published" or "Draft" (or blank), got "{status_raw}"',
                )
            )
            continue

        # Same duplicate rule as the staff UI / chat auto-promotion
        # (crud.faq.find_duplicate_faq) — an exact or reviewed-phrasing match
        # on the question text, never the row's database id, so a workbook
        # re-imported (or imported into another deployment) is recognized as
        # already present. The semantic near-duplicate check is skipped here
        # (no question_vector passed) to avoid an embedding call per row on a
        # bulk import.
        duplicate = await find_duplicate_faq(db, question, include_drafts=True)
        if duplicate is not None:
            summary.skipped += 1
            summary.errors.append(
                RowError(row_number=row_number, reason=f"Already exists as FAQ #{duplicate.id}; skipped")
            )
            continue

        try:
            category = await get_or_create_category_path(db, category_path) if category_path else None
            entry = await create_faq(
                db,
                question=question,
                answer=answer,
                category_id=category.id if category else None,
                image_urls=[image_url] if image_url else [],
                reference_urls=[reference_url] if reference_url else [],
                source="import",
                status=status,
            )
            await embed_entry(db, entry)
            await db.commit()
            summary.created += 1
        except Exception as exc:
            await db.rollback()
            summary.failed += 1
            summary.errors.append(RowError(row_number=row_number, reason=str(exc)))

    return summary


async def _import_library_sheet(db: AsyncSession, ws) -> ImportSummary:
    summary = ImportSummary()
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        return summary

    headers = [str(h).strip() if h is not None else "" for h in header_row]
    missing = [h for h in LIBRARY_REQUIRED_HEADERS if h not in headers]
    if missing:
        summary.failed += 1
        summary.errors.append(RowError(row_number=1, reason=f"Missing required column(s): {', '.join(missing)}"))
        return summary

    for row_number, row in enumerate(rows_iter, start=2):
        if row is None or all(cell is None for cell in row):
            continue
        cells = _row_cells(headers, row)
        category_path = cells.get("Category", "")
        title = cells.get("Title", "")
        content = cells.get("Content", "")
        tags_raw = cells.get("Tags", "")
        source_url = cells.get("Source URL", "")
        memory_raw = cells.get("Memory Enabled", "")

        missing_fields = [
            name for name, value in [("Category", category_path), ("Title", title), ("Content", content)] if not value
        ]
        if missing_fields:
            summary.skipped += 1
            summary.errors.append(
                RowError(row_number=row_number, reason=f"Missing required field(s): {', '.join(missing_fields)}")
            )
            continue

        try:
            category = await get_or_create_category_path(db, category_path)
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
            # Default to memory-enabled (searchable in chat) when the column is
            # blank, since the point of importing is to make this content
            # answerable again without recrawling — not to re-stage it as an
            # inert copy an admin has to remember to switch on.
            memory_enabled = memory_raw.strip().upper() != "FALSE" if memory_raw else True
            entry = await create_vault_entry(
                db,
                title=title,
                content=content,
                category_id=category.id,
                tags=tags,
                source_type="import",
                source_url=source_url or None,
            )
            entry.memory_enabled = memory_enabled
            if memory_enabled:
                await embed_vault_entry(db, entry)
            await db.commit()
            summary.created += 1
        except Exception as exc:
            await db.rollback()
            summary.failed += 1
            summary.errors.append(RowError(row_number=row_number, reason=str(exc)))

    return summary


async def _import_phrasing_sheet(db: AsyncSession, ws, created_by_id: int | None) -> ImportSummary:
    """Adds phrasings; never edits, disables or deletes existing ones, so a
    file that lacks a phrasing leaves it alone and re-importing the same file
    changes nothing. Each row goes through the same validation as a phrasing
    added in the staff UI (crud/faq_phrasing.create_phrasing): identifier and
    coverage rules, one wording -> one FAQ, not another FAQ's question.

    Rows with no Enabled value are stored disabled: only rows a reviewer
    marked TRUE (as every exported row is marked TRUE or FALSE) are served in
    chat, so a list of unreviewed, e.g. AI-suggested, wordings pasted into the
    sheet cannot go live just by being imported."""
    summary = ImportSummary()
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        return summary

    headers = [str(h).strip() if h is not None else "" for h in header_row]
    missing = [h for h in PHRASING_REQUIRED_HEADERS if h not in headers]
    if missing:
        summary.failed += 1
        summary.errors.append(RowError(row_number=1, reason=f"Missing required column(s): {', '.join(missing)}"))
        return summary

    for row_number, row in enumerate(rows_iter, start=2):
        if row is None or all(cell is None for cell in row):
            continue
        cells = _row_cells(headers, row)
        faq_question = cells.get("FAQ Question", "")
        text = cells.get("Phrasing", "")
        enabled_raw = cells.get("Enabled", "").upper()

        missing_fields = [name for name, value in [("FAQ Question", faq_question), ("Phrasing", text)] if not value]
        if missing_fields:
            summary.skipped += 1
            summary.errors.append(
                RowError(row_number=row_number, reason=f"Missing required field(s): {', '.join(missing_fields)}")
            )
            continue
        if enabled_raw not in ("", "TRUE", "FALSE"):
            summary.skipped += 1
            summary.errors.append(RowError(row_number=row_number, reason="Enabled must be TRUE, FALSE or blank"))
            continue

        try:
            matches = (
                await db.execute(
                    select(FAQEntry)
                    .where(FAQEntry.question_normalized == normalize_question(faq_question))
                    .order_by(FAQEntry.id)
                )
            ).scalars().all()
            if not matches:
                summary.failed += 1
                summary.errors.append(RowError(
                    row_number=row_number,
                    reason="No FAQ has this question (it must already exist or be in the FAQs sheet)",
                ))
                continue

            # Checked before the ambiguity below: the FAQs sheet has no
            # duplicate check of its own, so re-importing a workbook adds a
            # second FAQ with the same question, and the phrasing — already on
            # the original — must still count as present, not as an error.
            existing = (
                await db.execute(
                    select(FAQPhrasing).where(FAQPhrasing.phrasing_normalized == normalize_question(text))
                )
            ).scalars().first()
            if existing is not None and existing.faq_id in {faq.id for faq in matches}:
                summary.unchanged += 1  # already there; its current enabled state is kept
                continue

            if len(matches) > 1:
                ids = ", ".join(f"#{faq.id}" for faq in matches)
                summary.failed += 1
                summary.errors.append(RowError(
                    row_number=row_number,
                    reason=f"Several FAQs have this question ({ids}); remove the duplicates, then import again",
                ))
                continue
            faq = matches[0]

            await create_phrasing(db, faq, text, created_by_id=created_by_id, enabled=enabled_raw == "TRUE")
            summary.created += 1
        except Exception as exc:  # PhrasingError carries the same reason the staff UI shows
            await db.rollback()
            summary.failed += 1
            summary.errors.append(RowError(row_number=row_number, reason=str(exc)))

    return summary


async def import_knowledge_base(
    db: AsyncSession, file_bytes: bytes, created_by_id: int | None = None
) -> KnowledgeBaseImportSummary:
    try:
        wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as exc:
        error = ImportSummary(failed=1, errors=[RowError(row_number=0, reason=f"Could not read workbook: {exc}")])
        return KnowledgeBaseImportSummary(faqs=error, library=ImportSummary())

    faq_summary = (
        await _import_faq_sheet(db, wb[FAQ_SHEET_NAME]) if FAQ_SHEET_NAME in wb.sheetnames else ImportSummary()
    )
    library_summary = (
        await _import_library_sheet(db, wb[LIBRARY_SHEET_NAME])
        if LIBRARY_SHEET_NAME in wb.sheetnames
        else ImportSummary()
    )
    # After the FAQs sheet, so phrasings can point at FAQs created by this same file.
    phrasing_summary = (
        await _import_phrasing_sheet(db, wb[PHRASING_SHEET_NAME], created_by_id)
        if PHRASING_SHEET_NAME in wb.sheetnames
        else ImportSummary()
    )
    return KnowledgeBaseImportSummary(faqs=faq_summary, library=library_summary, phrasings=phrasing_summary)
