"""Météo des rumeurs: calendar rules worked out in code, never guessed by a model."""

from datetime import date

from app.core import seasons


def test_months_wrap_over_the_new_year():
    assert seasons.in_months(11, 4, 1) and seasons.in_months(11, 4, 11)
    assert not seasons.in_months(11, 4, 6)
    assert seasons.in_months(6, 6, 6) and not seasons.in_months(6, 6, 7)


def test_pay_day_rule_holds_only_around_the_end_of_the_month():
    assert seasons._in_days("Paie des fonctionnaires", 28)
    assert seasons._in_days("Paie des fonctionnaires", 3)
    assert not seasons._in_days("Paie des fonctionnaires", 15)
    assert seasons._in_days("Baccalauréat", 15)  # no day window


def test_regional_rules_only_show_where_they_apply():
    assert seasons._in_region("Peste", "Analamanga")
    assert not seasons._in_region("Peste", "Diana")
    assert seasons._in_region("Peste", None)
    assert seasons._in_region("Saison cyclonique", "Diana")


def test_a_verdict_comes_back_within_fifteen_days_of_the_same_date_in_an_earlier_year():
    today = date(2026, 11, 2)
    assert seasons.returns_on(date(2025, 10, 25), today)
    assert seasons.returns_on(date(2019, 11, 15), today)
    assert not seasons.returns_on(date(2025, 12, 1), today)
    assert not seasons.returns_on(date(2026, 10, 30), today)  # this year's, not one that returns
    # across the new year
    assert seasons.returns_on(date(2025, 12, 28), date(2027, 1, 5))


def test_elections_switch_on_from_the_date_the_newsroom_sets():
    today = date(2026, 11, 2)
    assert seasons._election({"election_date": "2026-12-15"}, today)["topic"] == "politique"
    assert seasons._election({"election_date": "2027-06-01"}, today) is None
    assert seasons._election({"election_date": "pas une date"}, today) is None
    assert seasons._election({}, today) is None


def test_keywords_tie_a_text_to_the_season():
    rules = [{"name": "Baccalauréat", "keywords": ["bac", "sujets"]}]
    assert seasons.matching(rules, "Les sujets du BAC auraient fuité") == ["Baccalauréat"]
    assert seasons.matching(rules, "Le pont est fermé") == []
    # whole words only: « tabac » is not the bac
    assert seasons.matching([{"name": "Bac", "keywords": ["bac"]}], "Hausse du tabac") == []
