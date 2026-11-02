"""The confidence score: computed from evidence, explained, never the model's own number."""

from datetime import timedelta

from app.core import confidence, dates

TODAY = dates.today()


def _src(n, kind="web", url=None, days_ago=None):
    return {
        "n": n,
        "kind": kind,
        "url": url,
        "date": (TODAY - timedelta(days=days_ago)).isoformat() if days_ago is not None else None,
    }


def _points(out):
    return {c["key"]: c["points"] for c in out["components"]}


def test_no_evidence_scores_zero_and_says_what_is_missing():
    out = confidence.compute([], [_src(1)], TODAY)
    assert out["score"] == 0 and out["level"] == "faible" and out["direction"] == "none"
    assert any("Aucun passage" in m for m in out["missing"])
    assert {c["key"] for c in out["components"]} == set(confidence.MAXIMA)
    assert out["meaning"] == "evidence_strength_not_truth_probability"


def test_pitch_like_facts_score_high_but_not_perfect_without_outside_sources():
    sources = [
        _src(1, "registry", "https://www.jirama.mg/communique-118", 1),
        _src(2, "figure", "https://ore.mg/tarifs", 20),
        _src(3, "archive", None, 3 * 365),
    ]
    evidence = [{"n": n, "stance": "contradicts"} for n in (1, 2, 3)]
    out = confidence.compute(evidence, sources, TODAY, {1, 2, 3})
    points = _points(out)
    assert points["agreement"] == 30 and points["official"] == 25 and points["outside"] == 0
    assert points["hosts"] == 10 and points["attached"] == 10
    assert 80 <= out["score"] < 95 and out["level"] == "eleve"
    assert out["direction"] == "contradicts"
    assert any("contredisent" in r for r in out["reasons"])
    assert any("extérieure" in m for m in out["missing"])


def test_mixed_stances_and_two_quotes_from_one_source_count_once():
    sources = [_src(1, url="https://a.example/x", days_ago=1), _src(2, url="https://b.example/y")]
    evidence = [
        {"result": 1, "stance": "supports"},
        {"result": 1, "stance": "supports"},
        {"result": 2, "stance": "contradicts"},
    ]
    out = confidence.compute(evidence, sources, TODAY)
    assert out["direction"] == "mixed"
    assert "1 source contredit, 1 confirme" == out["components"][0]["detail"]
    assert any("départager" in m for m in out["missing"])
    # a source that both supports and contradicts only nuances
    nuanced = confidence.compute(
        [{"n": 1, "stance": "supports"}, {"n": 1, "stance": "contradicts"}], sources, TODAY
    )
    assert nuanced["direction"] == "none"


def test_old_confirmations_lose_the_date_points():
    fresh = confidence.compute(
        [{"n": 1, "stance": "supports"}], [_src(1, url="https://a.example", days_ago=2)], TODAY
    )
    stale = confidence.compute(
        [{"n": 1, "stance": "supports"}], [_src(1, url="https://a.example", days_ago=400)], TODAY
    )
    assert _points(fresh)["dates"] == 15 and _points(stale)["dates"] < 15
    assert any("30 jours" in m for m in stale["missing"])


def test_official_hosts_from_the_annuaire_and_government_suffixes():
    ev = [{"n": 1, "stance": "supports"}]
    declared = confidence.compute(
        ev,
        [_src(1, url="https://www.jirama.mg/x", days_ago=0)],
        TODAY,
        official_hosts={"jirama.mg"},
    )
    assert _points(declared)["official"] == 25
    gov = confidence.compute(ev, [_src(1, url="https://sante.gov.mg/x", days_ago=0)], TODAY)
    assert _points(gov)["official"] == 25
    checker = confidence.compute(ev, [_src(1, url="https://factuel.afp.com/x", days_ago=0)], TODAY)
    assert _points(checker)["official"] == 20
    plain = confidence.compute(ev, [_src(1, url="https://blog.example/x", days_ago=0)], TODAY)
    assert _points(plain)["official"] == 5


def test_concerns_take_points_off():
    sources = [_src(n, url=f"https://s{n}.example", days_ago=0) for n in (1, 2, 3)]
    evidence = [{"n": n, "stance": "supports"} for n in (1, 2, 3)]
    clean = confidence.compute(evidence, sources, TODAY)
    doubted = confidence.compute(
        evidence,
        sources,
        TODAY,
        concerns=[{"quote": "x" * 10, "why": "La date est ancienne."}] * 4,
    )
    assert clean["score"] - doubted["score"] == 15
    assert "Le Contradicteur relève : La date est ancienne." in doubted["missing"]


def test_unknown_references_are_ignored():
    out = confidence.compute([{"n": 9, "stance": "supports"}], [_src(1)], "2026-01-01")
    assert out["score"] == 0
