"""Technical identifiers that make two similar-sounding questions different
questions.

Embedding similarity can't tell "E1" from "E4": measured on this knowledge
base, "my sauna screen says E1 and it wont heat up" scores 0.938 against a
genuine rewording of itself and 0.916 against the same sentence with E4 (and
SW3-45NS vs SW3-60NS scores 0.91). The ranges overlap, so no threshold can
separate them. Anything that reuses one question's answer for another must
therefore also check that their technical identifiers agree — that is what
`compatible` does.

No I/O here, so it is cheap enough to run on every candidate and easy to test.
"""

import re
from dataclasses import dataclass

# Product / controller names as staff write them. Matched as whole words,
# case-insensitively. Extend this tuple when a new product line's questions
# start needing to be told apart (the model-number and part patterns below
# already cover everything else generically).
PRODUCT_TERMS = ("innova", "saunova", "ste", "stn", "nb")

_PRODUCT_RE = re.compile(r"(?<![a-z0-9])(" + "|".join(PRODUCT_TERMS) + r")(?![a-z0-9])", re.I)

# "Error 13", "err 4", "Erro 9" (the source spreadsheet's own typo), "error code E4"
_ERROR_WORD_RE = re.compile(
    r"(?<![a-z0-9])err(?:or|o)?\s*(?:code|no\.?|number|#)?\s*e?\s*(\d{1,3})(?![a-z0-9])", re.I
)
# Bare display codes: E1, e13. Whole token only, so E1 never matches inside E13.
_BARE_CODE_RE = re.compile(r"(?<![a-z0-9])e(\d{1,3})(?![a-z0-9])", re.I)

# Letters+digits tokens: TS1, NTC2, F1, WJ3, SW3-45NS. Hyphenated ones are model
# numbers, the rest are component designators ("parts").
_ALNUM_TOKEN_RE = re.compile(r"(?<![a-z0-9])([a-z]{1,6}\d+(?:[-–][a-z0-9]+)*)(?![a-z0-9])", re.I)
# Digit-first model numbers such as 528-D. Needs a letter after the hyphen so
# plain ranges like "10-15" don't count.
_DIGIT_MODEL_RE = re.compile(r"(?<![a-z0-9])(\d{2,4}[-–][a-z][a-z0-9]*)(?![a-z0-9])", re.I)

# Display states that aren't E-codes. "oPEn" is matched case-exactly on
# purpose: the plain word "open" is everywhere in normal sentences, and a
# missed match only ever sends the question to the full pipeline (the safe
# direction).
_HEE_RE = re.compile(r"(?<![a-z0-9])hee(?![a-z0-9])", re.I)
_OPEN_RE = re.compile(r"(?<![A-Za-z0-9])oPEn(?![A-Za-z0-9])")
_DASHES_RE = re.compile(r"(?:-\s+){3,}-|-{4,}")
_LLPLN_RE = re.compile(r"(?<![a-z])l\s+l\s+p\s+l\s+n(?![a-z])", re.I)

# Numbers that carry a unit (55-65 ohm, 5 kohm, 19 C, 230 V). A question about
# 19 C is not a question about 25 C.
# The leading lookbehind keeps the "1" in "TS1" from being read as a value; the
# bare "c"/"f" alternatives cover people typing "19C" / "19 c" without a degree
# sign.
_UNIT_RE = re.compile(
    r"(?<![a-z0-9.,])(\d+(?:[.,]\d+)?)\s*(k\s?(?:ohms?|ω)|ohms?|ω|volts?|v|kw|w|hz|°\s?[cf]|celsius|mm|cm|kg|minutes?|mins?|seconds?|secs?|hours?|[cf])(?![a-z])",
    re.I,
)
_UNIT_CANON = {
    "kohm": "kohm", "kohms": "kohm", "kω": "kohm",
    "ohm": "ohm", "ohms": "ohm", "ω": "ohm",
    "volt": "v", "volts": "v", "v": "v",
    "°c": "c", "celsius": "c", "°f": "f",
    "minute": "min", "minutes": "min", "min": "min", "mins": "min",
    "second": "s", "seconds": "s", "sec": "s", "secs": "s",
    "hour": "h", "hours": "h",
}


# Observable symptoms that make two otherwise identical-sounding problems
# different problems: an NB heater that hums and one that clicks share the
# product and have no error code, so without this nothing would stop the
# "humming" answer being reused for "clicking". Word forms are listed
# explicitly (not prefixes) so "humidity" is never read as "hum". Based on the
# symptom vocabulary actually present in the knowledge base; extend as new
# troubleshooting content arrives.
_SYMPTOM_FORMS = {
    "HUM": ("hum", "hums", "humming", "hummed"),
    "BUZZ": ("buzz", "buzzes", "buzzing", "buzzed"),
    "CLICK": ("click", "clicks", "clicking", "clicked"),
    "RATTLE": ("rattle", "rattles", "rattling", "rattled"),
    "BEEP": ("beep", "beeps", "beeping", "beeped"),
    "WHISTLE": ("whistle", "whistles", "whistling"),
    "SMELL": ("smell", "smells", "smelling", "odor", "odour"),
    "SMOKE": ("smoke", "smokes", "smoking", "smoky"),
    "SPARK": ("spark", "sparks", "sparking", "arcing"),
    "LEAK": ("leak", "leaks", "leaking", "leaked", "leakage", "dripping"),
    "FLICKER": ("flicker", "flickers", "flickering"),
}
_SYMPTOM_RE = {
    name: re.compile(r"(?<![a-z])(" + "|".join(forms) + r")(?![a-z])", re.I)
    for name, forms in _SYMPTOM_FORMS.items()
}


@dataclass(frozen=True)
class TechnicalKey:
    codes: frozenset[str] = frozenset()  # E1, E13, HEE, OPEN, DASHES, LLPLN
    products: frozenset[str] = frozenset()  # INNOVA, SAUNOVA, STE, STN, NB
    models: frozenset[str] = frozenset()  # SW3-45NS, 528-D
    parts: frozenset[str] = frozenset()  # TS1, NTC2, F1
    units: frozenset[str] = frozenset()  # 5kohm, 19c
    symptoms: frozenset[str] = frozenset()  # HUM, CLICK, SMELL

    @property
    def is_empty(self) -> bool:
        return not (self.codes or self.products or self.models or self.parts or self.units or self.symptoms)

    def describe(self) -> str:
        if self.is_empty:
            return "none"
        fields = (
            ("codes", self.codes), ("products", self.products), ("models", self.models),
            ("parts", self.parts), ("units", self.units), ("symptoms", self.symptoms),
        )
        return " ".join(f"{name}={','.join(sorted(vals))}" for name, vals in fields if vals)


def extract_key(text: str) -> TechnicalKey:
    codes: set[str] = set()
    parts: set[str] = set()
    models: set[str] = set()

    for m in _ERROR_WORD_RE.finditer(text):
        codes.add(f"E{int(m.group(1))}")
    for m in _BARE_CODE_RE.finditer(text):
        codes.add(f"E{int(m.group(1))}")
    for m in _ALNUM_TOKEN_RE.finditer(text):
        token = m.group(1).upper().replace("–", "-")
        if re.fullmatch(r"E\d{1,3}", token):
            continue  # already recorded as a code
        (models if "-" in token else parts).add(token)
    for m in _DIGIT_MODEL_RE.finditer(text):
        models.add(m.group(1).upper().replace("–", "-"))

    if _HEE_RE.search(text):
        codes.add("HEE")
    if _OPEN_RE.search(text):
        codes.add("OPEN")
    if _DASHES_RE.search(text):
        codes.add("DASHES")
    if _LLPLN_RE.search(text):
        codes.add("LLPLN")

    units: set[str] = set()
    for m in _UNIT_RE.finditer(text):
        unit = re.sub(r"\s+", "", m.group(2).lower())
        number = m.group(1).replace(",", ".")
        units.add(f"{float(number):g}{_UNIT_CANON.get(unit, unit)}")

    products = {m.group(1).upper() for m in _PRODUCT_RE.finditer(text)}
    symptoms = {name for name, pattern in _SYMPTOM_RE.items() if pattern.search(text)}

    return TechnicalKey(
        codes=frozenset(codes),
        products=frozenset(products),
        models=frozenset(models),
        parts=frozenset(parts),
        units=frozenset(units),
        symptoms=frozenset(symptoms),
    )


def compatible(query: TechnicalKey, candidate: TechnicalKey) -> tuple[bool, str]:
    """(ok, reason-if-not). Error codes, products and model numbers must agree
    exactly — a saved answer for Innova E1 is not the answer to Saunova E1 or
    to Innova E4. Component designators (TS1, NTC2) and unit-bearing numbers
    only have to agree when both sides mention them: a question that just says
    "E1" hasn't contradicted a saved question that also names TS1, but "TS1"
    vs "TS2" is a real conflict. Symptoms follow the same rule (humming vs
    clicking conflicts; no symptom mentioned does not)."""
    if query.codes != candidate.codes:
        return False, f"codes differ ({_fmt(query.codes)} vs {_fmt(candidate.codes)})"
    if query.products != candidate.products:
        return False, f"products differ ({_fmt(query.products)} vs {_fmt(candidate.products)})"
    if query.models != candidate.models:
        return False, f"models differ ({_fmt(query.models)} vs {_fmt(candidate.models)})"
    if query.parts and candidate.parts and query.parts != candidate.parts:
        return False, f"parts differ ({_fmt(query.parts)} vs {_fmt(candidate.parts)})"
    if query.units and candidate.units and query.units != candidate.units:
        return False, f"values differ ({_fmt(query.units)} vs {_fmt(candidate.units)})"
    if query.symptoms and candidate.symptoms and query.symptoms != candidate.symptoms:
        return False, f"symptoms differ ({_fmt(query.symptoms)} vs {_fmt(candidate.symptoms)})"
    return True, ""


def _fmt(values: frozenset[str]) -> str:
    return ",".join(sorted(values)) or "none"
