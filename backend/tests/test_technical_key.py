import pytest

from app.rag.technical_key import compatible, extract_key


def _ok(a: str, b: str) -> bool:
    return compatible(extract_key(a), extract_key(b))[0]


def test_same_question_reworded_is_compatible():
    assert _ok(
        "my sauna screen says E1 and it wont heat up",
        "what happens my sauna screen says E1 and it wont heat up what could be the reason of this",
    )


@pytest.mark.parametrize("other", ["E4", "E13", "E2", "E10"])
def test_different_error_code_is_never_compatible(other):
    # "E1" must not match inside "E13"/"E10" either.
    assert not _ok("my sauna screen says E1 and it wont heat up", f"my sauna screen says {other} and it wont heat up")


def test_error_word_forms_normalise_to_the_same_code():
    for text in ("Error 13", "error 13", "Err 13", "error code E13", "E13", "e13"):
        assert extract_key(text).codes == {"E13"}, text
    # the source spreadsheet's own typo
    assert extract_key("Erro 9 (E9)").codes == {"E9"}


def test_status_codes_are_distinct_from_error_codes():
    assert not _ok("my sauna screen says E1 and it wont heat up", "sauna display says oPEn and heater won't start")
    assert extract_key("the screen shows HeE").codes == {"HEE"}
    assert extract_key('display shows "- - - -"').codes == {"DASHES"}
    assert extract_key("keeps showing L L P L N").codes == {"LLPLN"}
    # the ordinary word must not be read as the display code
    assert extract_key("the door is open").codes == frozenset()


def test_controller_names_must_agree():
    assert not _ok("Saunova E7 communication error", "Innova E7 communication error")
    assert not _ok("STN E6 water level too high", "STE E6 fill failure")
    assert _ok("Saunova E7 communication error", "how do I troubleshoot the E7 communication error on Saunova")


def test_model_numbers_must_agree():
    assert not _ok("What is the SW3-45NS heater power?", "What is the SW3-60NS heater power?")
    assert _ok("What is the SW3-45NS heater power?", "SW3-45NS power rating?")
    assert not _ok("Details on the Siro bench 528-D", "Details on the Siro bench 528-E")


def test_component_designators_conflict_only_when_both_named():
    assert not _ok("TS1 is not connected", "TS2 is not connected")
    assert not _ok("NTC1 resistance", "NTC2 resistance")
    # a plain "E1" asker hasn't contradicted a saved question that also names TS1
    assert _ok("Customer has Error 1 on an Innova", "Innova Power Controller Error 1 (E1) - Temperature Sensor 1 (TS1) is not connected")


def test_values_with_units_must_agree_when_both_present():
    assert not _ok("what should the resistance be at 19 C", "what should the resistance be at 25 C")
    assert extract_key("55 - 65 Ω and 5kΩ").units == {"65ohm", "5kohm"}
    assert _ok("resistance reading?", "resistance reading at 19 °C?")


def test_plain_ranges_are_not_model_numbers():
    assert extract_key("wait 10-15 minutes").models == frozenset()


def test_free_text_has_an_empty_key():
    assert extract_key("What is SAWO?").is_empty
    assert extract_key("tell me about moisture paper").is_empty
