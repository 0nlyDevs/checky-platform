"""Chiffres: numbers read from a text by code and set against dated, sourced official figures."""

from datetime import timedelta

from app.core import dates
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


DELESTAGE = {
    "topic": "énergie",
    "label": "Délestage programmé à Antananarivo",
    "value": "4",
    "unit": "h/jour",
    "as_of": (dates.today() - timedelta(days=1)).isoformat(),  # yesterday, whatever the run date
    "country": "Madagascar",
    "place": "Antananarivo",
    "source_name": "JIRAMA, communiqué N° 2026-118 (démo)",
    "source_url": "https://example.org/communique",
    "keywords": ["délestage", "coupure", "électricité", "jirama"],
}
TARIF = {
    "topic": "énergie",
    "label": "Hausse du tarif de l'électricité",
    "value": "+12",
    "unit": "%",
    "as_of": "2026-10",
    "country": "Madagascar",
    "source_name": "ORE (démo)",
    "source_url": "https://example.org/ore",
    "keywords": ["tarif", "électricité", "hausse"],
}


def _seed_shared():
    import asyncio

    from app.core.db import SessionLocal
    from app.modules.figures import seed_shared

    async def go():
        async with SessionLocal() as db:
            await seed_shared(db)
            await seed_shared(db)
            await db.commit()

    asyncio.run(go())


def test_the_pitch_numbers_differ_from_the_official_figures(as_user):
    from tests.test_workspaces import _workspace

    alice = as_user("alice")
    ws = _workspace(alice)
    base = f"/api/v1/workspaces/{ws}/figures"
    created = alice.post(base, json=DELESTAGE)
    assert created.status_code == 201
    assert created.json()["location"]["region"] == "Analamanga" and not created.json()["shared"]
    assert alice.post(base, json=TARIF).json()["as_of_label"] == "octobre 2026"
    _seed_shared()
    checked = alice.post(f"{base}/check", json={"text": RUMOUR}).json()
    assert [(c["claimed"], c["verdict"]) for c in checked] == [
        ("72 heures", "differs"),
        ("40 %", "differs"),
    ]
    hours, percent = checked
    assert hours["figure"]["label"] == DELESTAGE["label"] and hours["figure"]["value"] == "4"
    assert percent["figure"]["value"] == "+12" and percent["figure"]["unit"] == "%"
    assert "Le chiffre officiel dit +12 %" in percent["summary"]
    assert hours["figure"]["old"] is False and hours["figure"]["age_days"] == 1


def test_matches_old_figures_unknown_numbers_and_other_countries(as_user):
    from tests.test_workspaces import _workspace

    alice, bob = as_user("alice"), as_user("bob")
    ws, other = _workspace(alice), _workspace(bob)
    _seed_shared()
    listed = alice.get(f"/api/v1/workspaces/{ws}/figures").json()
    census = next(f for f in listed if "RGPH-3" in f["label"])
    assert census["shared"] and census["old"] and census["as_of_label"] == "2018"
    assert len([f for f in listed if f["label"] == "Population totale"]) == 1
    assert (
        alice.get(f"/api/v1/workspaces/{ws}/figures", params={"topic": "énergie"}).json()[0]["unit"]
        == "%"
    )

    def check(text):
        return alice.post(f"/api/v1/workspaces/{ws}/figures/check", json={"text": text}).json()

    population = check("Madagascar compte 33 millions d'habitants.")[0]
    assert population["verdict"] == "matches" and population["figure"]["as_of"] == "2025"
    assert check("L'inflation atteint 15 % cette année.")[0]["verdict"] == "differs"
    assert check("3 cas de peste à Ambositra")[0]["verdict"] == "no_figure"
    assert "ne prouve rien" in check("3 cas de peste")[0]["summary"]
    assert check("En France, l'inflation atteint 8,1 %.")[0]["verdict"] == "no_figure"
    assert check("40 % de la population n'a pas de jiro")[0]["verdict"] == "differs"
    assert check("Rien à compter ici.") == []
    # A newsroom's own figures stay its own.
    alice.post(f"/api/v1/workspaces/{ws}/figures", json=TARIF)
    assert not any(
        f["label"] == TARIF["label"] for f in bob.get(f"/api/v1/workspaces/{other}/figures").json()
    )


def test_figures_refresh_pulls_world_bank_values_into_shared_figures(as_user):
    import asyncio

    import httpx

    from app.workers import figures_refresh, queue
    from tests.test_workspaces import _workspace

    calls = []

    def answer(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        indicator = request.url.path.rsplit("/", 1)[-1]
        if indicator == "FP.CPI.TOTL.ZG":
            return httpx.Response(503)
        rows = [
            {"country": {"id": "MG"}, "date": "2025", "value": 32800000},
            {"country": {"id": "KM"}, "date": "2024", "value": 900000},
            {"country": {"id": "MU"}, "date": "2025", "value": None},
            {"country": {"id": "SN"}, "date": "2025", "value": 18900000},
        ]
        return httpx.Response(200, json=[{"page": 1}, rows])

    alice, bob = as_user("alice"), as_user("bob")
    ws = _workspace(alice)
    from tests.test_newsroom_resources import invite

    invite(alice, ws, bob)
    # A newsroom in Senegal: its country's figures come too.
    alice.patch(f"/api/v1/workspaces/{ws}", json={"settings": {"country": "Sénégal"}})
    original = figures_refresh._transport
    figures_refresh._transport = httpx.MockTransport(answer)
    try:
        job = alice.post(f"/api/v1/workspaces/{ws}/figures/refresh")
        assert job.status_code == 202
        assert asyncio.run(queue.run_once()) is True
    finally:
        figures_refresh._transport = original
    done = alice.get(f"/api/v1/workspaces/{ws}/jobs/{job.json()['job_id']}").json()
    assert done["status"] == "done" and done["result"]["failed"] == ["FP.CPI.TOTL.ZG"]
    assert "mrnev=1" in calls[0]
    assert "MG;KM;MU;SC;FR;SN" in calls[0] or "MG%3BKM%3BMU%3BSC%3BFR%3BSN" in calls[0]
    listed = alice.get(f"/api/v1/workspaces/{ws}/figures", params={"q": "Population totale"}).json()
    mg = next(f for f in listed if f["country"] == "Madagascar")
    assert mg["value"] == "32 800 000" and mg["as_of"] == "2025" and mg["shared"]
    assert mg["source_url"] == "https://data.worldbank.org/indicator/SP.POP.TOTL?locations=MG"
    assert any(f["country"] == "Sénégal" for f in listed)
    assert any(f["country"] == "Comores" and f["value"] == "900 000" for f in listed)
    # The seeded inflation value stays when the API fails.
    inflation = alice.get(f"/api/v1/workspaces/{ws}/figures", params={"q": "Inflation"}).json()
    assert inflation[0]["value"] == "8,1"
