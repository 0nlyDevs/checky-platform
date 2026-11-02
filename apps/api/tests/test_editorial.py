from app.core.editorial import clean_framing


def test_framing_requires_verbatim_quotes_and_explicit_political_target():
    text = "Le Parti Bleu est un désastre. Regardez ceci !"
    signal = {
        "kind": "political_framing",
        "quote": "Le Parti Bleu est un désastre.",
        "target": "Parti Bleu",
        "explanation": "Formulation hostile, pas une preuve de fausseté.",
    }
    assert clean_framing({"signals": [signal]}, text) == [signal]
    assert clean_framing({"signals": [{**signal, "target": "Parti Rouge"}]}, text) == []
    assert (
        clean_framing({"signals": [{**signal, "quote": "Le Parti Bleu est corrompu."}]}, text) == []
    )
    assert clean_framing({"signals": [{**signal, "target": ""}]}, text) == []
