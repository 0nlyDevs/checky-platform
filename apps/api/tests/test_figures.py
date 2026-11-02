"""Chiffres: numbers read from a text by code and set against dated, sourced official figures."""

from app.core.numbers import extract_numbers, parse_figure, same

RUMOUR = (
    "URGENT ⚠️ COMMUNIQUÉ N° 2026-118 de la JIRAMA : délestage de 72 heures à partir du 3 novembre "
    "sur tout Antananarivo, hausse de 40 % du tarif en décembre. Partagez à tous vos contacts !!!"
)


def test_numbers_with_a_unit_are_read_with_their_kind_and_clause():
    found = extract_numbers(RUMOUR)
    assert [(n["claimed"], n["kind"]) for n in found] == [
        ("72 heures", "duration"),
        ("40 %", "percent"),
    ]
    hours, percent = found
    assert hours["base"] == 72 and hours["per"] is None
    assert "délestage" in hours["clause"] and "tarif" not in hours["clause"]
    assert (
        percent["direction"] == "up" and percent["clause"] == "hausse de 40 % du tarif en décembre"
    )
    # The reference number, the date and the year are not claims.
    assert not any("2026" in n["claimed"] or "novembre" in n["claimed"] for n in found)


def test_counts_amounts_rates_and_times_of_day():
    def read(text):
        return [(n["claimed"], n["kind"], n["base"], n["per"]) for n in extract_numbers(text)]

    assert read("Madagascar compte 30 millions d'habitants") == [
        ("30 millions d'habitants", "count", 30e6, None)
    ]
    assert read("3 cas de peste à Ambositra") == [("3 cas", "count", 3, None)]
    assert read("le kilo est vendu 3 300 ariary le kilo") == [
        ("3 300 ariary le kilo", "amount", 3300, "kilo")
    ]
    assert read("2,5 milliards d'ariary") == [("2,5 milliards d'ariary", "amount", 2.5e9, None)]
    assert read("4 h/jour") == [("4 h/jour", "duration", 4, "jour")]
    assert read("3 jours de coupure")[0][2] == 72
    # Clock times are not durations.
    assert read("coupure à 6 h et jusqu'à 23h47") == []
    assert extract_numbers("baisse de 12 %")[0]["direction"] == "down"


def test_same_allows_the_rounding_a_person_does_and_nothing_more():
    population = parse_figure("32 740 678", "habitants")
    assert same(extract_numbers("33 millions d'habitants")[0], population)
    assert same(extract_numbers("32,7 millions d'habitants")[0], population)
    assert not same(extract_numbers("30 millions d'habitants")[0], population)
    rise = parse_figure("+12", "%")
    assert rise["kind"] == "percent" and rise["direction"] == "up"
    assert same(extract_numbers("hausse de 12 %")[0], rise)
    assert not same(extract_numbers("baisse de 12 %")[0], rise)
    assert not same(extract_numbers("hausse de 40 %")[0], rise)
    per_day = parse_figure("4", "h/jour")
    assert not same(extract_numbers("72 heures")[0], per_day)
    assert same(extract_numbers("4 heures par jour")[0], per_day)
    assert same(extract_numbers("3 jours")[0], parse_figure("72", "heures"))
