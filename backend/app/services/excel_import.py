import io
from dataclasses import dataclass, field

from openpyxl import Workbook, load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.category import build_category_path_map, get_or_create_category_path
from app.crud.faq import create_faq, find_duplicate_faq, list_faqs_all
from app.rag.reindex import embed_entry
from app.services.kb_export import parse_faq_status, text_cells_only

TEMPLATE_HEADERS = ["Category", "Question", "Answer", "Image URL", "Reference URL", "Status"]
REQUIRED_HEADERS = ["Category", "Question", "Answer"]


def generate_template() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "FAQ Import"
    ws.append(TEMPLATE_HEADERS)
    ws.append(
        [
            "Billing",
            "How do I update my payment method?",
            "Go to Account Settings > Billing and click 'Update Payment Method'.",
            "",
            "https://example.com/billing-help",
            "Published",
        ]
    )
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


async def export_faqs(
    db: AsyncSession,
    category_id: int | None = None,
    search: str | None = None,
    include_drafts: bool = True,
) -> bytes:
    """Export FAQ entries (optionally filtered) using the same column layout as
    the import template, so the file can be edited and re-imported."""
    status_filter = None if include_drafts else "published"
    entries = await list_faqs_all(db, category_id=category_id, search=search, status_filter=status_filter)
    category_paths = await build_category_path_map(db)

    wb = Workbook()
    ws = wb.active
    ws.title = "FAQ Export"
    ws.append(TEMPLATE_HEADERS)

    for entry in entries:
        category_path = category_paths.get(entry.category_id, "") if entry.category_id else ""
        ws.append(
            [
                category_path,
                entry.question,
                entry.answer,
                (entry.image_urls or [""])[0],
                (entry.reference_urls or [""])[0],
                entry.status,
            ]
        )

    text_cells_only(ws)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


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


async def import_workbook(db: AsyncSession, file_bytes: bytes) -> ImportSummary:
    summary = ImportSummary()

    try:
        wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as exc:
        summary.errors.append(RowError(row_number=0, reason=f"Could not read workbook: {exc}"))
        summary.failed += 1
        return summary

    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)

    try:
        header_row = next(rows_iter)
    except StopIteration:
        summary.errors.append(RowError(row_number=0, reason="Workbook is empty"))
        summary.failed += 1
        return summary

    headers = [str(h).strip() if h is not None else "" for h in header_row]
    missing = [h for h in REQUIRED_HEADERS if h not in headers]
    if missing:
        summary.errors.append(
            RowError(row_number=1, reason=f"Missing required column(s): {', '.join(missing)}")
        )
        summary.failed += 1
        return summary

    col_index = {h: i for i, h in enumerate(headers)}

    for row_number, row in enumerate(rows_iter, start=2):
        if row is None or all(cell is None for cell in row):
            continue

        def cell(name: str) -> str:
            idx = col_index.get(name)
            if idx is None or idx >= len(row):
                return ""
            value = row[idx]
            return str(value).strip() if value is not None else ""

        category_path = cell("Category")
        question = cell("Question")
        answer = cell("Answer")
        image_url = cell("Image URL")
        reference_url = cell("Reference URL")
        status_raw = cell("Status")

        # Category is optional: FAQEntry.category_id is nullable, and the
        # staff FAQ editor already creates FAQs with no category (category_id:
        # null is its default) — a blank cell means "no category", not an
        # error, so it must not be in this required-field check.
        missing_fields = []
        if not question:
            missing_fields.append("Question")
        if not answer:
            missing_fields.append("Answer")

        if missing_fields:
            summary.skipped += 1
            summary.errors.append(
                RowError(
                    row_number=row_number,
                    reason=f"Missing required field(s): {', '.join(missing_fields)}",
                )
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

        # Same duplicate rule the staff UI and chat auto-promotion already use
        # (crud.faq.find_duplicate_faq): an exact or reviewed-phrasing match on
        # the question text, not the row's database id — so re-importing the
        # same workbook, or a workbook exported from a different deployment,
        # is recognized as already present instead of creating a copy. The
        # semantic near-duplicate check (question_vector) is intentionally not
        # used here: it needs an embedding call per row, which a bulk import
        # shouldn't pay for on every row just to catch reworded duplicates.
        duplicate = await find_duplicate_faq(db, question, include_drafts=True)
        if duplicate is not None:
            summary.skipped += 1
            summary.errors.append(
                RowError(
                    row_number=row_number,
                    reason=f"Already exists as FAQ #{duplicate.id}; skipped",
                )
            )
            continue

        try:
            category = await get_or_create_category_path(db, category_path) if category_path else None
            image_urls = [image_url] if image_url else []
            reference_urls = [reference_url] if reference_url else []
            entry = await create_faq(
                db,
                question=question,
                answer=answer,
                category_id=category.id if category else None,
                image_urls=image_urls,
                reference_urls=reference_urls,
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
