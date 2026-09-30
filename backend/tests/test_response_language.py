"""Response language, exercised through the real pipeline.

Reproduces the live failure: an English warranty question answered in
Chinese. The stub model here behaves the way the live one did: it follows an
explicit "write your reply in X" instruction when the prompt has one, and
otherwise drifts into the language of its context (or into a Chinese apology
when it has nothing to say)."""

import re

import pytest

from app.db.vec_store import VAULT_VEC_TABLE, upsert_embedding
from app.models.vault_entry import VaultEntry
from app.rag import pipeline
from app.rag.filler import is_filler
from app.rag.response_language import answer_matches, detect
from tests.conftest import ANGLES, add_faq, vector_for
from tests.conftest import angle as _angle

CJK = re.compile(r"[一-鿿]")

EN_ANSWER = "The SW3-45NS has a 2-year warranty. Error E1 means TS1 is not connected; TS1 should read 5 kohm at 25 °C (4.5 kW model)."
ZH_ANSWER = "SW3-45NS 的保修期为 2 年。错误 E1 表示 TS1 未连接；TS1 在 25 °C 时应为 5 kohm（4.5 kW 型号）。"
ZH_APOLOGY = "抱歉，我在资料中没有找到关于保修的信息。"

EN_PAGE_TITLE = "Warranty (EN)"
EN_PAGE = "SAWO heaters carry a 2-year warranty from the date of purchase."
ZH_PAGE_TITLE = "Warranty (ZH)"
ZH_PAGE = "SAWO 加热器自购买之日起享有 2 年保修。"

EN_QUESTION = "What is the warranty on SAWO heaters?"
ZH_REQUEST = "What is the warranty on SAWO heaters? Please answer in Chinese."
ZH_QUESTION = "SAWO 加热器的保修期是多久？"
GREETING = "hello"

ANGLES.update({
    EN_PAGE_TITLE: 20.0,
    ZH_PAGE_TITLE: 20.0,
    EN_QUESTION: 20.0 + _angle(0.8),
    ZH_REQUEST: 20.0 - _angle(0.8),
    ZH_QUESTION: 20.0 + _angle(0.79),
})


class DriftingLLM:
    """Replies in the language the system prompt names; with no instruction, in
    the language of its context. `stubborn` ignores instructions entirely."""

    name = "drifting"

    def __init__(self, stubborn: str | None = None):
        self.stubborn = stubborn
        self.calls: list[tuple[str, str, str]] = []

    async def generate(self, system, context, question, temperature=0, history=None):
        self.calls.append((system, context, question))
        if system.startswith("You are a fact-checker"):
            return "GROUNDED"
        if system.startswith("You classify"):
            return "YES"
        if self.stubborn is not None:
            return self.stubborn
        wanted = re.search(r"Write your entire reply in (\w+)", system)
        if wanted and wanted.group(1) == "Chinese":
            return ZH_ANSWER
        if wanted and wanted.group(1) == "the":  # "in the same language as the user's message"
            return ZH_ANSWER if CJK.search(question) else EN_ANSWER
        if wanted:
            return EN_ANSWER
        return ZH_ANSWER if CJK.search(context) else EN_ANSWER


@pytest.fixture
def drifting(monkeypatch):
    holder = {"llm": DriftingLLM()}

    async def _get(_db):
        return holder["llm"]

    monkeypatch.setattr(pipeline, "get_active_engine", _get)
    return holder


async def add_page(db, title, content):
    entry = VaultEntry(title=title, content=content, source_url=f"https://www.sawo.com/{len(title)}/", memory_enabled=True)
    db.add(entry)
    await db.commit()
    await upsert_embedding(db, VAULT_VEC_TABLE, entry.id, vector_for(title))


# --- detection -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question, name, script, explicit",
    [
        ("What is the warranty on the SW3-45NS?", "English", "latin", False),
        ("what kW is the SW3-45NS", "English", "latin", False),
        ("SW3-45NS 的功率是多少？", "Chinese", "han", False),
        ("What is the warranty? Please answer in Chinese.", "Chinese", "han", True),
        ("Explain E1 in simplified Chinese please", "Chinese", "han", True),
        ("请用中文回答：SW3-45NS 的保修期", "Chinese", "han", True),
        ("Can you tell me if the manual is available in Chinese?", "English", "latin", False),
        ("Wat is de garantie op de kachel?", None, "latin", False),
        ("Mikä on kiukaan takuu? Vastaa suomeksi", "Finnish", "latin", True),
    ],
)
def test_detect(question, name, script, explicit):
    lang = detect(question)
    assert (lang.name, lang.script, lang.explicit) == (name, script, explicit)


def test_answer_matches_checks_the_writing_system():
    english, chinese = detect(EN_QUESTION), detect(ZH_REQUEST)
    assert answer_matches(EN_ANSWER, english) and not answer_matches(ZH_ANSWER, english)
    assert not answer_matches(ZH_APOLOGY, english)
    assert answer_matches(ZH_ANSWER, chinese) and not answer_matches(EN_ANSWER, chinese)


# --- pipeline ---------------------------------------------------------------------------


async def test_english_question_and_english_sources_get_english(db, embedder, drifting):
    await add_page(db, EN_PAGE_TITLE, EN_PAGE)
    result = await pipeline.answer_question(db, EN_QUESTION, session_id="s-en")
    assert not result.is_fallback and result.answer == EN_ANSWER


async def test_english_question_with_chinese_sources_still_gets_english(db, embedder, drifting):
    await add_page(db, ZH_PAGE_TITLE, ZH_PAGE)
    result = await pipeline.answer_question(db, EN_QUESTION, session_id="s-zhsrc")
    assert not result.is_fallback and result.answer == EN_ANSWER
    system, context, _q = drifting["llm"].calls[-1]
    assert CJK.search(context)  # the source really was Chinese
    assert "Write your entire reply in English" in system


async def test_a_model_that_ignores_the_instruction_never_shows_chinese_to_an_english_question(db, embedder, drifting):
    drifting["llm"] = DriftingLLM(stubborn=ZH_ANSWER)
    await add_page(db, ZH_PAGE_TITLE, ZH_PAGE)
    result = await pipeline.answer_question(db, EN_QUESTION, session_id="s-stubborn")
    assert result.is_fallback and not CJK.search(result.answer)


async def test_english_warranty_question_never_gets_a_chinese_fallback(db, embedder, drifting):
    drifting["llm"] = DriftingLLM(stubborn=ZH_APOLOGY)  # a refusal written as a Chinese apology
    await add_page(db, EN_PAGE_TITLE, EN_PAGE)
    result = await pipeline.answer_question(db, EN_QUESTION, session_id="s-apology")
    assert result.is_fallback and not CJK.search(result.answer)
    assert result.answer.startswith("Thanks for your question")


async def test_explicitly_requested_chinese_is_produced(db, embedder, drifting):
    await add_page(db, EN_PAGE_TITLE, EN_PAGE)
    result = await pipeline.answer_question(db, ZH_REQUEST, session_id="s-zhreq")
    assert not result.is_fallback and result.answer == ZH_ANSWER
    assert "Write your entire reply in Chinese, as the user asked" in drifting["llm"].calls[-1][0]


async def test_a_chinese_question_gets_chinese(db, embedder, drifting):
    await add_page(db, EN_PAGE_TITLE, EN_PAGE)
    result = await pipeline.answer_question(db, ZH_QUESTION, session_id="s-zhq")
    assert not result.is_fallback and result.answer == ZH_ANSWER


def test_non_latin_questions_are_not_mistaken_for_small_talk():
    assert not is_filler(ZH_QUESTION) and not is_filler("加热器的保修期是多久？")
    assert is_filler("hello") and is_filler("ok") and is_filler("？？")


async def test_product_names_codes_and_measurements_are_unchanged(db, embedder, drifting):
    await add_page(db, EN_PAGE_TITLE, EN_PAGE)
    en = await pipeline.answer_question(db, EN_QUESTION, session_id="s-ids-en")
    zh = await pipeline.answer_question(db, ZH_REQUEST, session_id="s-ids-zh")
    for token in ("SW3-45NS", "E1", "TS1", "5 kohm", "25 °C", "4.5 kW"):
        assert token in en.answer and token in zh.answer
    assert "Copy product names, model numbers, error and display codes" in drifting["llm"].calls[-1][0]


async def test_off_topic_reply_follows_the_same_rule(db, embedder, drifting):
    drifting["llm"] = DriftingLLM(stubborn="你好！我很好，谢谢。请问有什么产品或技术问题需要帮助吗？")
    result = await pipeline.answer_question(db, GREETING, session_id="s-hello")
    assert result.is_fallback and not CJK.search(result.answer)
    assert result.answer.startswith("I'm here to help")  # the configured off-topic message


# --- audit regressions ---------------------------------------------------------------

E1_FAQ_Q = "Innova display shows E1 and the heater won't heat, what does it mean?"
E1_FAQ_A = "E1 means Temperature Sensor 1 (TS1) is not connected. Check the TS1 wiring."
E1_ASK_ZH = "Innova display shows E1 and the heater won't heat, what does it mean? Please answer in Chinese."
E1_IN_ZH = "Innova 显示 E1，加热器不加热，这是什么意思？"

ANGLES.update({E1_FAQ_Q: 24.0, E1_ASK_ZH: 24.0 + _angle(0.96), E1_IN_ZH: 24.0 - _angle(0.95)})


@pytest.mark.parametrize("question", [E1_ASK_ZH, E1_IN_ZH])
async def test_saved_english_answers_are_not_served_to_another_language(db, embedder, drifting, question):
    await add_faq(db, E1_FAQ_Q, E1_FAQ_A)
    result = await pipeline.answer_question(db, question, session_id="s-saved-zh")
    assert result.engine_used != "faq_direct" and result.answer != E1_FAQ_A


async def test_saved_answer_still_serves_the_english_question(db, embedder, drifting):
    await add_faq(db, E1_FAQ_Q, E1_FAQ_A)
    result = await pipeline.answer_question(db, E1_FAQ_Q, session_id="s-saved-en")
    assert result.engine_used == "faq_direct" and result.answer == E1_FAQ_A


@pytest.mark.parametrize("question", ["保修期", "保修多久", "价格？", "E1是什么"])
def test_short_chinese_questions_are_not_small_talk(question):
    assert not is_filler(question)
