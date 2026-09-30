"""Which retrieved knowledge-base content applies to the product a question names.

Similarity search can't tell products apart: the NB heater's humming FAQ scores
as well against "my SW3-45NS is humming" as against an NB question, because
only the model code differs. The generation prompt used to be the only
defence, and a cheap model reading NB troubleshooting in its context applied
it to the SW3-45NS (the fact-check only asks whether each claim appears in the
context, which it did). So an explicit model or controller in the question is
treated as a hard constraint on the context, decided here, before generation.

A chunk's *scope* is the heater models and product labels it names. A question
with a scope may only be answered from chunks that are
  * general (name no model or product at all), or
  * about one of the question's models (SW3-45NS matches SW3-45NS-P-C), or,
    when they name no model, share one of the question's labels (an NB
    question and NB content; content naming both NB and NS serves both, which
    is how documentation that explicitly covers several products stays usable).
A chunk scoped only to other models or products is dropped. There is one
documented link on top of that: the question's model's own product page lists
the controllers it takes ("Available controls: Saunova/Innova"), so content
scoped to those controllers applies to it too.

That link is deliberately split into two questions, both answered here:
"which controllers does this model support" (linked_controllers — a set of
labels, used to admit controller-scoped chunks past the filter above) and
"which page said so" (linked_controller_pages — the actual page(s), for a
caller that needs to show its work). A controller-scoped chunk carries no
mention of the model itself, so a context built only from linked_controllers'
say-so gives a reader — human or fact-checking model — no way to verify the
claim that it applies; linked_controller_pages exists so the pipeline can
include the one page that actually ties them together, as evidence, without
promoting it to ranked answer content in its own right.

No I/O here except linked_controllers'/linked_controller_pages' shared,
single indexed query; no AI calls.
"""

import re
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vault_entry import VaultEntry
from app.rag.technical_key import extract_key

# SAWO product codes: family, hyphen, power digits, then (for heaters) the
# control-variant suffix and option codes. Group 1 is the code without its
# option codes (SW3-45NS-P-C and SW3-45NS-WL-P-C are both the SW3-45NS, and
# "SW3-45NS-based" must not become a different model), group 2 the variant.
# Two shapes:
#   * family letters+digits — SW3-45NS-P-C, ARI3-60NB, CUB3-45NI2-P-C,
#     SP02-900. Distinctive enough to match in any case, and the variant is
#     optional so a bare "SW3-45" still names a model;
#   * family letters only — HES-45NS-G-P-C, SCAC-60NS-Z-C, TRDC-90/120NS-G-P.
#     Needs the variant and upper case (as the documentation writes codes),
#     or "mid-60s" would read as a model.
# technical_key's model pattern misses the second shape, hence a separate one.
# Digit-first article numbers ("392-D", and noise like "15-minute") never
# scope anything.
_MODEL_RES = (
    re.compile(r"(?<![a-z0-9])([a-z]{1,6}\d{1,2}-\d{2,3}([a-z]+\d?)?)(?![a-z0-9])", re.I),
    re.compile(r"(?<![A-Za-z0-9])([A-Z]{2,6}-\d{2,3}(?:/\d{2,3})*([A-Z]+\d?))(?![A-Za-z0-9])"),
)

# Control variants as written on their own ("SAWO30 Round NS", "(NS)"). NB is
# also one of technical_key's PRODUCT_TERMS; NS and Ni2 are not, because they
# have never needed telling apart for saved answers.
_VARIANT_RE = re.compile(r"(?<![a-z0-9])(nb|ns|ni2)(?![a-z0-9])", re.I)
_VARIANTS = {"NB", "NS", "NI2"}


@dataclass(frozen=True)
class Scope:
    models: frozenset[str] = frozenset()  # SW3-45NS
    labels: frozenset[str] = frozenset()  # INNOVA, NB, NS

    @property
    def is_empty(self) -> bool:
        return not (self.models or self.labels)

    def describe(self) -> str:
        """Human-readable target for prompts and messages: models when the
        question names any (their variant is implied), otherwise labels."""
        names = sorted(self.models) or sorted(self._display_labels())
        return ", ".join(names)

    def _display_labels(self) -> set[str]:
        return {_display(label) for label in self.labels}


def _display(label: str) -> str:
    return label if label in _VARIANTS or label in {"STE", "STN"} else label.capitalize()


def scope_of(text: str, *, text_labels: bool = True) -> Scope:
    """text_labels=False reads only model codes (and the variants they
    carry), ignoring product names mentioned in running text."""
    text = text.replace("–", "-")
    models: set[str] = set()
    labels: set[str] = set()
    if text_labels:
        labels |= extract_key(text).products
        labels |= {m.group(1).upper() for m in _VARIANT_RE.finditer(text)}
    for pattern in _MODEL_RES:
        for m in pattern.finditer(text):
            models.add(m.group(1).upper())
            if m.group(2):
                labels.add(m.group(2).upper())
    return Scope(models=frozenset(models), labels=frozenset(labels))


# Library chunks harvested from the website (source_type "library") repeat the
# site's navigation menu — "... Innova Series ... Nordex Mini Ni2 ... Saunova
# Series" — so product names in their text say nothing about what the page
# covers: read that way, the privacy policy and the general FAQ page were
# Innova/Saunova/Ni2 documentation, hidden from every NB or steam question. A
# harvested page's product is in its title and URL ("/aries-corner-nb/") and
# its model codes. Imported and manually written entries have no boilerplate
# and are read in full.
HARVESTED_SOURCE_TYPE = "library"


def vault_scope(title: str, source_url: str | None, content: str, source_type: str | None) -> Scope:
    head = f"{title}\n{source_url or ''}"
    if source_type != HARVESTED_SOURCE_TYPE:
        return scope_of(f"{head}\n{content}")
    identity, body = scope_of(head), scope_of(content, text_labels=False)
    return Scope(models=identity.models | body.models, labels=identity.labels | body.labels)


def _model_matches(a: str, b: str) -> bool:
    """SW3-45NS matches SW3-45NS-P-C (and SW3-45 matches both SW3-45NS and
    SW3-45NB), but SW3-45NS never matches SW3-45NB or SW3-450…"""
    if a == b:
        return True
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return long_.startswith(short) and not long_[len(short)].isdigit()


def applies(question: Scope, chunk: Scope, linked_labels: frozenset[str] = frozenset()) -> bool:
    if question.is_empty or chunk.is_empty:
        return True
    if question.models:
        if any(_model_matches(qm, cm) for qm in question.models for cm in chunk.models):
            return True
        if chunk.models:
            return False  # another model's own documentation
    return bool((question.labels | linked_labels) & chunk.labels)


def other_labels(question: Scope, excluded: list[Scope], linked_labels: frozenset[str] = frozenset()) -> list[str]:
    """What the dropped content was about, for the limitation message."""
    found = set()
    for scope in excluded:
        found |= scope.labels - question.labels - linked_labels
    return sorted(_display(label) for label in found)


async def _linked_pages(db: AsyncSession, question: Scope) -> list[tuple[VaultEntry, Scope]]:
    """Library pages that name one of the question's models, together with
    each page's own scope — the shared lookup behind linked_controllers()
    (which only needs the controller labels) and linked_controller_pages()
    (which needs the pages themselves, to cite as relationship evidence)."""
    if not question.models:
        return []
    result = await db.execute(
        select(VaultEntry)
        .where(
            VaultEntry.memory_enabled.is_(True),
            or_(*[VaultEntry.content.contains(model) for model in question.models]),
        )
        .limit(20)
    )
    matches = []
    for entry in result.scalars():
        page = vault_scope(entry.title, entry.source_url, entry.content, entry.source_type)
        if any(_model_matches(qm, pm) for qm in question.models for pm in page.models):
            matches.append((entry, page))
    return matches


async def linked_controllers(db: AsyncSession, question: Scope) -> frozenset[str]:
    """Controllers that the question's model's own Library pages name (the
    product page lists which controls the heater takes). Variants are not
    carried over: an NS page that links a shared NS/NB manual does not make
    NB troubleshooting apply to an NS heater."""
    controllers: set[str] = set()
    for _entry, page in await _linked_pages(db, question):
        controllers |= page.labels - _VARIANTS
    return frozenset(controllers)


async def linked_controller_pages(db: AsyncSession, question: Scope) -> list[VaultEntry]:
    """The question model's own product page(s) that document a controller
    (e.g. "Available controls: Saunova/Innova (NS)") — the authoritative
    evidence that content scoped to that controller (kept in context via
    linked_controllers, above) actually applies to this model. Retrieval
    ranks by semantic similarity to the question, which a product's own spec
    page can easily score too low on to reach the answer context even though
    it establishes the relationship a controller FAQ needs — this lets a
    caller include that page deliberately when that relationship was used,
    regardless of its retrieval score."""
    return [entry for entry, page in await _linked_pages(db, question) if page.labels - _VARIANTS]
