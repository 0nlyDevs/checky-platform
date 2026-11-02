"""Tone and danger read in code: verbatim quotes, three languages, no model."""

from app.core import tone
from app.modules.demo import DEMO_RUMOUR_TEXT


def test_pitch_rumour_is_sensational_with_verbatim_quotes():
    out = tone.analyse(DEMO_RUMOUR_TEXT)
    assert out["level"] == "sensationnaliste"
    kinds = {s["kind"] for s in out["signals"]}
    assert {"urgency", "share", "exclamations", "emoji"} <= kinds
    assert all(s["quote"] in DEMO_RUMOUR_TEXT for s in out["signals"])
    quotes = {s["quote"] for s in out["signals"]}
    assert "URGENT" in quotes and "Partagez" in quotes
    # JIRAMA and COMMUNIQUÉ are not enough capitals to call the whole text shouting
    assert "caps" not in kinds


def test_neutral_text_and_acronyms_are_not_shouting():
    text = "La JIRAMA et l'INSTAT publient leurs chiffres du mois de septembre."
    assert tone.analyse(text) == {
        "level": "neutre",
        "signals": [],
        "caps_ratio": 0.0,
        "exclamations": 0,
    }


def test_shouting_malagasy_and_english_words_are_found():
    text = "VAOVAO MAFANA !!! Zarao aminareo rehetra fa MAIKA"
    out = tone.analyse(text)
    kinds = {s["kind"] for s in out["signals"]}
    assert {"urgency", "share", "exclamations", "caps"} <= kinds
    assert out["level"] == "sensationnaliste"
    english = tone.analyse("Breaking: they don't want you to know this. Share it.")
    assert {"urgency", "hidden", "share"} <= {s["kind"] for s in english["signals"]}


def test_one_emotive_word_is_marked_not_sensational():
    out = tone.analyse("Un rapport scandaleux sur la gestion des déchets.")
    assert out["level"] == "marqué"
    assert out["signals"] == [{"kind": "emotive", "quote": "scandaleux"}]


def test_accents_typed_or_not_are_found_and_quoted_as_written():
    out = tone.risk("Delestage annonce sur tout le quartier")
    assert out["reasons"] == [{"kind": "panic", "quote": "Delestage"}]


def test_risk_levels():
    pitch = tone.risk(DEMO_RUMOUR_TEXT)
    assert pitch["level"] == "high"  # a power cut presented as a JIRAMA communiqué
    assert {r["kind"] for r in pitch["reasons"]} == {"panic", "fake_order"}
    assert all(r["quote"] in DEMO_RUMOUR_TEXT for r in pitch["reasons"])
    assert tone.risk("Il faut lynchez ce sorcier")["level"] == "high"
    assert tone.risk("Une pénurie de riz annoncée")["level"] == "medium"
    assert tone.risk("Le marché rouvre lundi") == {"level": "low", "reasons": [], "by": "code"}
    # « a été arrêté » (arrested) is not an official order
    assert tone.risk("Le suspect a été arrêté hier")["level"] == "low"


def test_language():
    assert tone.language(DEMO_RUMOUR_TEXT) == "fr"
    assert tone.language("Tsy misy jiro ny tanàna sy ny manodidina, hoy izay nanao") == "mg"
    assert tone.language("The bridge is closed and the road will stay shut") == "en"
    assert tone.language("12 34") == "other"
