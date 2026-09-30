import pytest

from app.rag.answer_style import strip_source_talk


@pytest.mark.parametrize(
    "raw, expected",
    [
        # the exact reply from the screenshot
        (
            'Based on the context, for the sauna heater display, "L L P L N" means: Muddled Letters in the Touch Interface.\n\n'
            "Possible causes and fixes from the knowledge base:\n\n"
            "- **Cause:** Forced shutdown.\n  **Solution:** Long-press OK.",
            'For the sauna heater display, "L L P L N" means: Muddled Letters in the Touch Interface.\n\n'
            "- **Cause:** Forced shutdown.\n  **Solution:** Long-press OK.",
        ),
        ("Based on the information available, the E1 error means TS1 is not connected.", "The E1 error means TS1 is not connected."),
        ("Based on the provided information, an E1 error can have these causes:", "An E1 error can have these causes:"),
        ("According to the internal knowledge base: replace the sensor.", "Replace the sensor."),
        ("Possible causes and fixes from the documented information:\n- a\n- b", "- a\n- b"),
        ("Possible causes and fixes:\n\n- a", "- a"),
        ("Troubleshooting steps from the documentation:\n- a", "- a"),
        ("The causes, as listed in the knowledge base, are:\n- a", "The causes are:\n- a"),
        ("Check the TS1 wiring (from the knowledge base).", "Check the TS1 wiring."),
    ],
)
def test_source_talk_is_removed(raw, expected):
    assert strip_source_talk(raw) == expected


@pytest.mark.parametrize(
    "answer",
    [
        'E1 means "Temperature Sensor 1 (TS1) is not connected".',
        "- **Cause:** Loose wiring.\n  **Solution:** Retighten the terminal blocks.",
        "Based on the E1 error alone you cannot tell which wire is loose.",  # not about sources
        "The resistance should read 4.5kΩ - 5.1kΩ.",
        "Use the information on the display to confirm the code.",  # 'information' used normally
    ],
)
def test_real_answers_are_left_alone(answer):
    assert strip_source_talk(answer) == answer


def test_never_returns_empty():
    assert strip_source_talk("Possible causes and fixes:") == "Possible causes and fixes:"
