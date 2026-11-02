from app.core.editorial import clean_framing, evidence_audit, transparency


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


def test_snippets_do_not_inflate_documentation_and_bias_never_changes_score():
    source = {
        "n": 1,
        "url": "https://news.example/a",
        "date": "2020-01-01",
        "snippet": "Something",
        "read_status": "not_read",
    }
    audit = evidence_audit([source], [{"result": 1, "stance": "supports"}])
    assert audit["score"] == 0 and audit["not_read"] == [1]
    read = {**source, "read_status": "read", "passages": ["Something"]}
    audit = evidence_audit([read], [{"result": 1, "stance": "contradicts"}])
    assert audit["score"] == 55  # 10 read + 10 cited + 25 dated + 10 host
    assert audit["meaning"] == "documentation_completeness_not_truth_probability"
    assert audit["independence"] == "not_established"
    assert evidence_audit([read], [{"result": 1, "stance": "supports"}])["score"] == 55


def test_unknown_publisher_properties_are_not_failures():
    data = transparency({}, "An article without extracted metadata.")
    assert data["author"] is None
    assert data["ownership"] == data["political_leaning"] == "not_assessed"
