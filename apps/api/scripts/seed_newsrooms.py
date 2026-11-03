"""Seed two newsrooms with real Malagasy rumours, their real sources and the verdicts that the
published fact-checks reached. The newsrooms and their journalists are invented; the claims, the
articles and the conclusions are not (every verdict follows what the cited press reported, and no
real person is named in a claim).

    # the web app must be running (accounts are created through Better Auth's sign-up)
    cd apps/api && uv run python scripts/seed_newsrooms.py --web http://localhost:3000
    DATABASE_URL="$PROD_DATABASE_URL" uv run python scripts/seed_newsrooms.py \
        --web https://checky-mg.vercel.app --accounts ~/checky-seed-accounts.txt

Options: --reset deletes the seeded newsrooms (by slug) first; --no-wait queues the page reads and
analyses without waiting for the API's workers. The journalists' passwords are written to the
--accounts file only (never commit it). Links are read by the API's own `ingest_url` jobs; a page
that refuses the reader keeps the journalist's note on it instead.
"""

import argparse
import asyncio
import json
import secrets
import sys
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select, text

import app.main  # noqa: F401 - registers every job handler
from app.core.db import SessionLocal
from app.core.models import Activity, Comment, Item, MemberPref, Membership, Source, Workspace
from app.core.refs import next_ref
from app.modules import signing
from app.workers.queue import enqueue

EAT = timedelta(hours=3)
NOW = datetime.now(UTC)


def at(day: str, hour: str = "08:00") -> datetime:
    """A Madagascar date and time as UTC."""
    return datetime.fromisoformat(f"{day}T{hour}:00").replace(tzinfo=UTC) - EAT


def ago(hours: float) -> datetime:
    return NOW - timedelta(hours=hours)


TANA = {"name": "Antananarivo", "region": "Analamanga", "country": "MG"}
MAHAJANGA = {"name": "Mahajanga", "region": "Boeny", "country": "MG"}
MADAGASCAR = {"name": "Madagascar", "country": "MG"}

NEWSROOMS = [
    {
        "slug": "le-veilleur-antananarivo",
        "name": "Le Veilleur d'Antananarivo",
        "settings": {
            "country": "MG",
            "timezone": "Indian/Antananarivo",
            "ai_enabled": True,
            "beats": ["économie", "énergie", "éducation", "santé", "société", "sécurité"],
        },
        "regions": ["Analamanga"],
        "people": [
            ("Hanitra Rakotomalala", "hanitra.rakotomalala@veilleur.test"),
            ("Tojo Randrianarisoa", "tojo.randrianarisoa@veilleur.test"),
            ("Fanja Razafindrabe", "fanja.razafindrabe@veilleur.test"),
        ],
    },
    {
        "slug": "radio-andrefana-mahajanga",
        "name": "Radio Andrefana Mahajanga",
        "settings": {
            "country": "MG",
            "timezone": "Indian/Antananarivo",
            "ai_enabled": True,
            "beats": ["santé", "sécurité", "économie", "société"],
        },
        "regions": ["Boeny"],
        "people": [
            ("Mamy Andriamihaja", "mamy.andriamihaja@andrefana.test"),
            ("Voahirana Rasolofo", "voahirana.rasolofo@andrefana.test"),
        ],
    },
]

# Each dossier: newsroom slug, who opened it (index in that newsroom's people), when the rumour was
# first seen, the claim as it circulated, status, verdict (only for signed ones), the reason
# signed, origin, tags, place, the sources (url, title, the journalist's note on it, used when the
# page refuses the reader), the comments (author index, text, hours after first seen), the
# assignee, and whether the AI analysis should run once the sources are read.
DOSSIERS = [
    {
        "ws": "le-veilleur-antananarivo",
        "by": 0,
        "seen": at("2024-11-15", "09:20"),
        "title": "Le ministère de l'Économie et des Finances verse une aide de 450 000 ariary à chaque ménage",
        "status": "published",
        "verdict": "false",
        "reason": "Le ministère de l'Économie et des Finances a dénoncé ces messages comme frauduleux : aucune aide de 450 000 ariary n'est versée, il s'agit d'une tentative d'escroquerie.",
        "origin": "facebook",
        "tags": ["économie", "arnaque"],
        "place": MADAGASCAR,
        "signed_after": 30,
        "sources": [
            (
                "https://midi-madagasikara.mg/reseaux-sociaux-des-messages-frauduleux-et-des-tentatives-descroquerie-denonces-par-le-mef/",
                "Réseaux sociaux : des messages frauduleux et des tentatives d'escroquerie, dénoncés par le MEF",
                "Midi Madagasikara rapporte que le ministère de l'Économie et des Finances dénonce des messages frauduleux diffusés sur les réseaux sociaux, dont un faux message promettant une aide de 450 000 ariary : une tentative d'escroquerie.",
            ),
            (
                "https://fr.allafrica.com/stories/202411180462.html",
                "Madagascar : Réseaux sociaux - Des messages frauduleux et des tentatives d'escroquerie, dénoncés par le MEF",
                "Reprise par allAfrica : le MEF met en garde contre de faux messages d'aide financière circulant sur les réseaux sociaux.",
            ),
        ],
        "comments": [
            (
                1,
                "Le même visuel tourne dans trois groupes Facebook de quartier, avec un lien vers un formulaire.",
                2,
            ),
            (
                0,
                "Le MEF vient de publier sa mise en garde. On peut signer : faux, et on rappelle de ne jamais donner ses coordonnées.",
                26,
            ),
        ],
    },
    {
        "ws": "le-veilleur-antananarivo",
        "by": 1,
        "seen": at("2024-05-21", "17:40"),
        "title": "Le directeur général de la JIRAMA a démissionné",
        "status": "published",
        "verdict": "false",
        "reason": "La JIRAMA a démenti par un communiqué : son directeur général assure toujours ses fonctions.",
        "origin": "facebook",
        "tags": ["énergie"],
        "place": TANA,
        "signed_after": 20,
        "sources": [
            (
                "https://madagascar-tribune.com/Ron-Weiss-assure-ses-fonctions-et-devrait-faire-face-a-de-nombreux-defis.html",
                "La Jirama dément la démission de son directeur général",
                "Madagascar Tribune, 22 mai 2024 : dans un bref communiqué, la JIRAMA dément les informations sur la démission de son directeur général, qui assure ses fonctions.",
            ),
        ],
        "comments": [
            (
                2,
                "Aucune source officielle derrière les publications, seulement des captures d'écran.",
                1,
            ),
            (1, "Communiqué de la JIRAMA reçu ce matin, je joins l'article.", 15),
        ],
    },
    {
        "ws": "le-veilleur-antananarivo",
        "by": 2,
        "seen": at("2024-07-22", "21:05"),
        "title": "Les sujets du bac 2024 sont en vente sur Facebook la veille des épreuves",
        "status": "published",
        "verdict": "false",
        "reason": "Les « sujets » vendus sur Facebook étaient des faux, et le ministère a démenti toute fuite des sujets officiels.",
        "origin": "facebook",
        "tags": ["éducation"],
        "place": MADAGASCAR,
        "signed_after": 16,
        "sources": [
            (
                "https://www.afrik.com/madagascar-l-apparition-de-faux-sujets-du-bac-sur-facebook-fait-polemique",
                "Madagascar : l'apparition de faux sujets du bac sur Facebook fait polémique",
                "Afrik.com : de faux sujets du baccalauréat ont été vendus sur Facebook à la veille des épreuves ; le ministère a démenti toute fuite des sujets officiels.",
            ),
            (
                "https://fr.allafrica.com/stories/202407230168.html",
                "Madagascar : Un trafic sur Facebook de faux sujets du bac fait polémique",
                "allAfrica : un trafic de faux sujets du bac sur Facebook ; démenti du ministère sur toute fuite des sujets officiels.",
            ),
        ],
        "comments": [
            (
                0,
                "Des parents nous écrivent pour savoir s'ils doivent payer. Priorité ce soir.",
                0.5,
            ),
            (
                2,
                "Les pages vendent des PDF différents d'un groupe à l'autre. Ça ressemble à une arnaque.",
                3,
            ),
        ],
    },
    {
        "ws": "le-veilleur-antananarivo",
        "by": 1,
        "seen": at("2025-07-02", "10:15"),
        "title": "Recrutement d'inspecteurs des douanes : 650 000 ariary à payer pour s'inscrire au concours",
        "status": "published",
        "verdict": "false",
        "reason": "L'administration des douanes indique qu'aucun recrutement d'inspecteurs n'est en cours ; les vrais concours sont annoncés sur les sites et pages officiels du ministère et de la Direction générale des douanes.",
        "origin": "facebook",
        "tags": ["société", "arnaque"],
        "place": MADAGASCAR,
        "signed_after": 28,
        "sources": [
            (
                "https://www.moov.mg/actualite/103585-recrutement-douane-une-arnaque-bien-rodee",
                "Recrutement Douanes : une arnaque bien rodée",
                "Moov.mg : une page Facebook se faisant passer pour la Direction générale des douanes annonce un concours d'inspecteurs et réclame 650 000 ariary d'inscription. L'administration dément tout recrutement en cours.",
            ),
        ],
        "comments": [
            (1, "La page a été créée il y a deux semaines et utilise le logo des douanes.", 1),
        ],
    },
    {
        "ws": "le-veilleur-antananarivo",
        "by": 0,
        "seen": at("2019-01-23", "14:30"),
        "title": "La Banque centrale va mettre en circulation des billets de 50 000 et 100 000 ariary",
        "status": "published",
        "verdict": "false",
        "reason": "La Banky Foiben'i Madagasikara a qualifié ces informations de suppositions et a porté plainte contre leurs auteurs ; aucune coupure de ce montant n'a été annoncée.",
        "origin": "facebook",
        "tags": ["économie"],
        "place": MADAGASCAR,
        "signed_after": 40,
        "sources": [
            (
                "https://lexpress.mg/25/01/2019/nouveau-billet-de-banque-les-initiateurs-des-rumeurs-recherches/",
                "Nouveau billet de banque : les initiateurs des rumeurs recherchés",
                "L'Express de Madagascar, 25 janvier 2019 : la Banque centrale qualifie les rumeurs de nouvelles coupures de 50 000 et 100 000 ariary de simples suppositions et a porté plainte contre leurs instigateurs.",
            ),
            (
                "https://upload.wikimedia.org/wikipedia/commons/c/c7/Ariary.JPG",
                "Photo : billets en ariary (Wikimedia Commons, Marc Baronnet, CC BY-SA 3.0)",
                "Billets en ariary actuellement en circulation, pour comparaison.",
            ),
        ],
        "comments": [
            (
                2,
                "Le visuel du « nouveau billet » est un montage : la typographie ne correspond à aucune série de la BFM.",
                6,
            ),
        ],
    },
    {
        "ws": "le-veilleur-antananarivo",
        "by": 2,
        "seen": at("2026-10-22", "11:00"),
        "title": "La Banque centrale émet des billets commémoratifs de 10 000 et 20 000 ariary pour le centenaire de la monnaie",
        "status": "published",
        "verdict": "true",
        "reason": "Annonce confirmée : la Banky Foiben'i Madagasikara émettra des billets commémoratifs de 10 000 et 20 000 ariary pour le centenaire de la première coupure malgache, sans augmenter la quantité de monnaie en circulation.",
        "origin": "press",
        "tags": ["économie"],
        "place": MADAGASCAR,
        "signed_after": 6,
        "sources": [
            (
                "https://www.moov.mg/article/123039-centenaire-de-la-monnaie-malgache-de-nouveaux-billets-de-10-000-et-20-000-ariary-annonces",
                "Centenaire de la monnaie malgache : de nouveaux billets de 10 000 et 20 000 ariary annoncés",
                "Moov.mg, 22 octobre 2026 : la BFM émettra des billets commémoratifs de 10 000 et 20 000 ariary pour le centenaire ; l'opération renouvelle des billets usagés sans augmenter la masse monétaire.",
            ),
        ],
        "comments": [
            (
                0,
                "Après les fausses annonces de 2019, on vérifie à la source. Cette fois c'est la BFM elle-même.",
                2,
            ),
        ],
    },
    {
        "ws": "le-veilleur-antananarivo",
        "by": 1,
        "seen": at("2026-10-14", "07:45"),
        "title": "Les motards qui roulent sur les trottoirs d'Antananarivo risquent trois à dix jours de prison",
        "status": "published",
        "verdict": "false",
        "reason": "Le Code municipal d'hygiène prévoit la mise en fourrière des motos sur les trottoirs, mais aucune peine de prison.",
        "origin": "whatsapp",
        "tags": ["société", "sécurité"],
        "place": TANA,
        "signed_after": 30,
        "sources": [
            (
                "https://www.lexpress.mg/2026/10/reseaux-sociaux-la-desinformation.html",
                "Réseaux sociaux : la désinformation accentue les tensions",
                "L'Express de Madagascar, 28 octobre 2026 : parmi les 212 cas relevés du 10 au 16 octobre par le monitoring MDM, une rumeur annonçait trois à dix jours de prison pour les motocyclistes sur les trottoirs ; le Code municipal d'hygiène prévoit la fourrière, sans incarcération.",
            ),
            (
                "https://www.lexpress.mg/2026/10/antananarivo-la-circulation-se.html",
                "Antananarivo : la circulation se réorganise",
                "L'Express de Madagascar : la Commune urbaine dégage les trottoirs ; dans le troisième arrondissement, des motos ont été mises en fourrière pour stationnement irrégulier.",
            ),
        ],
        "comments": [
            (
                0,
                "Message vocal en malgache qui circule sur WhatsApp, repris par deux pages. Qui appelle la CUA ?",
                1,
            ),
            (
                1,
                "La CUA confirme la fourrière, rien sur la prison. Le texte du Code municipal va dans le même sens.",
                22,
            ),
        ],
    },
    {
        "ws": "le-veilleur-antananarivo",
        "by": 0,
        "seen": at("2026-10-05", "19:10"),
        "title": "La coupure de courant pendant le discours présidentiel à Ambohijatovo était un sabotage",
        "status": "in_progress",
        "origin": "facebook",
        "tags": ["énergie", "politique"],
        "place": TANA,
        "assignee": 1,
        "analyze": True,
        "sources": [
            (
                "https://fr.allafrica.com/stories/202610060207.html",
                "Madagascar : Délestage en plein discours présidentiel - Excuses publiques de la Jirama",
                "allAfrica, 6 octobre 2026 : la JIRAMA présente ses excuses et attribue la coupure à une insuffisance de puissance sur une ligne haute tension de 35 kV.",
            ),
            (
                "https://www.madagascar-tribune.com/Delestages-la-Jirama-s-excuse-au-president-mais-qu-en-est-il-des-Malgaches.html",
                "Délestages : la Jirama s'excuse au président, mais qu'en est-il des Malgaches ?",
                "Madagascar Tribune revient sur les excuses de la JIRAMA après la coupure et sur les délestages subis par les ménages.",
            ),
            (
                "https://upload.wikimedia.org/wikipedia/commons/1/12/JIRAMA_Mahajanga_2025.jpg",
                "Photo : agence JIRAMA (Wikimedia Commons, Promo2024, CC0)",
                "Photo d'illustration d'une agence JIRAMA, partagée avec certaines publications.",
            ),
        ],
        "comments": [
            (
                0,
                "Les publications parlent de sabotage sans aucun élément. La JIRAMA parle d'une ligne 35 kV.",
                14,
            ),
            (
                1,
                "Je demande au service de communication de la JIRAMA si un incident technique a été relevé ce soir-là.",
                16,
            ),
        ],
    },
    {
        "ws": "le-veilleur-antananarivo",
        "by": 2,
        "seen": at("2026-10-31", "13:30"),
        "title": "Treize centres d'arnaque en ligne démantelés à Madagascar, 52 millions de dollars en cryptomonnaies gelés",
        "status": "published",
        "verdict": "true",
        "reason": "Plusieurs médias rapportent le démantèlement de treize centres d'escroquerie en ligne et le gel de 52 millions de dollars en cryptomonnaies ; ils divergent sur la date de l'opération (fin juillet, ou août-septembre).",
        "origin": "press",
        "tags": ["sécurité", "économie"],
        "place": MADAGASCAR,
        "signed_after": 5,
        "sources": [
            (
                "https://la1ere.franceinfo.fr/mayotte/une-apparente-traite-d-etres-humains-derriere-les-centres-d-arnaques-en-ligne-demanteles-a-madagascar-1753881.html",
                "Une apparente traite d'êtres humains derrière les centres d'arnaques en ligne démantelés à Madagascar",
                "Outre-mer La 1ère : les centres d'arnaque démantelés à Madagascar auraient exploité des travailleurs étrangers attirés par de fausses offres d'emploi.",
            ),
            (
                "https://journalducoin.com/actualites/crypto-madagascar-fermes-arnaques-demantelees",
                "Crypto : 52 millions de dollars saisis à Madagascar, 13 fermes à arnaques démantelées",
                "Journal du Coin : 13 centres démantelés, 52 millions de dollars en cryptomonnaies gelés et 3 200 appareils saisis.",
            ),
        ],
        "comments": [
            (
                2,
                "Les chiffres concordent d'une source à l'autre, pas les dates. On le dit dans la conclusion.",
                3,
            ),
        ],
    },
    {
        "ws": "radio-andrefana-mahajanga",
        "by": 0,
        "seen": at("2026-01-01", "18:00"),
        "title": "Cinq cas de mpox confirmés à Mahajanga",
        "status": "published",
        "verdict": "true",
        "reason": "Le ministère de la Santé publique a confirmé des cas de mpox à Mahajanga ; le BNGRC a publié la situation et les mesures de prévention.",
        "origin": "radio",
        "tags": ["santé"],
        "place": MAHAJANGA,
        "signed_after": 20,
        "sources": [
            (
                "https://fr.allafrica.com/stories/202601020129.html",
                "Madagascar : Cinq cas confirmés de mpox à Majunga, selon le ministère de la Santé publique",
                "allAfrica, 2 janvier 2026 : le ministère de la Santé publique confirme cinq cas de mpox à Mahajanga.",
            ),
            (
                "https://bngrc.gov.mg/mpox-variole-du-singe-situation-sanitaire-a-mahajanga-et-mesures-de-prevention/",
                "Mpox (variole du singe) : situation sanitaire à Mahajanga et mesures de prévention",
                "Le BNGRC publie la situation sanitaire à Mahajanga et les mesures de prévention contre le mpox.",
            ),
            (
                "https://upload.wikimedia.org/wikipedia/commons/4/4c/Mahajanga_hopital_manaram_penitra.jpg",
                "Photo : hôpital de Mahajanga (Wikimedia Commons, Francis de Chambure, CC BY-SA 3.0)",
                "Photo d'illustration de l'hôpital de Mahajanga.",
            ),
        ],
        "comments": [
            (
                1,
                "Les auditeurs appellent depuis ce matin. On attend le chiffre officiel avant l'antenne de 18 h.",
                1,
            ),
            (
                0,
                "Le ministère confirme. On passe l'info avec les gestes de prévention du BNGRC.",
                18,
            ),
        ],
    },
    {
        "ws": "radio-andrefana-mahajanga",
        "by": 1,
        "seen": ago(20),
        "title": "La justice américaine demande l'extradition de six suspects de fraude aux cryptomonnaies arrêtés à Madagascar",
        "status": "in_progress",
        "origin": "press",
        "tags": ["sécurité", "économie"],
        "place": MADAGASCAR,
        "assignee": 1,
        "analyze": True,
        "sources": [
            (
                "https://la1ere.franceinfo.fr/reunion/madagascar-la-justice-americaine-demande-l-extradition-de-six-suspects-de-fraudes-aux-cryptomonnaies-1753821.html",
                "Madagascar : la justice américaine demande l'extradition de six suspects de fraudes aux cryptomonnaies",
                "Outre-mer La 1ère, 2 novembre 2026 : la justice américaine demande l'extradition de six suspects de fraude aux cryptomonnaies.",
            ),
            (
                "https://www.moov.mg/article/123527-escroquerie-internationale-madagascar-au-coeur-dune-enquete-americaine",
                "Escroquerie internationale : Madagascar au cœur d'une enquête américaine",
                "Moov.mg : Madagascar au cœur d'une enquête américaine sur une escroquerie internationale.",
            ),
        ],
        "comments": [
            (
                1,
                "Des auditeurs disent que des jeunes de Mahajanga sont parmi les suspects. Rien ne le dit dans les articles pour l'instant.",
                2,
            ),
        ],
    },
]

# The publication date of the pages that refuse the reader (the others carry their own).
NOTE_DATES = {
    "https://midi-madagasikara.mg/reseaux-sociaux-des-messages-frauduleux-et-des-tentatives-descroquerie-denonces-par-le-mef/": "2024-11-18",
    "https://fr.allafrica.com/stories/202411180462.html": "2024-11-18",
    "https://www.afrik.com/madagascar-l-apparition-de-faux-sujets-du-bac-sur-facebook-fait-polemique": "2024-07-23",
    "https://fr.allafrica.com/stories/202407230168.html": "2024-07-23",
}

# Tips sent by the public (they arrive in the newsroom of the region where the rumour circulates).
TIPS = [
    {
        "ws": "le-veilleur-antananarivo",
        "seen": ago(3),
        "text": "SMS reçu : le ministère des Finances verse 450 000 ariary d'aide, il faut envoyer son nom et son numéro pour la recevoir. C'est vrai ?",
        "origin": "sms",
        "place": TANA,
    },
    {
        "ws": "le-veilleur-antananarivo",
        "seen": ago(9),
        "text": "Sur Facebook on dit que les motos sur le trottoir à Analakely partent en prison dès lundi",
        "origin": "facebook",
        "place": TANA,
    },
]


def log(db, ws, actor: str, item_id, action: str, when: datetime, diff: dict | None = None) -> None:
    """The dossier's history, dated when it happened (not when the seed ran)."""
    db.add(
        Activity(
            workspace_id=ws,
            actor_id=actor,
            entity="item",
            entity_id=item_id,
            action=action,
            diff=diff or {},
            created_at=when,
        )
    )


def sign_up(web: str, name: str, email: str, password: str) -> bool:
    """Create the account; False when it already exists (it keeps its own password)."""
    req = urllib.request.Request(
        f"{web.rstrip('/')}/api/auth/sign-up/email",
        data=json.dumps({"name": name, "email": email, "password": password}).encode(),
        headers={"Content-Type": "application/json", "Origin": web.rstrip("/")},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=30).read()
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        if e.code == 422 or "already" in body.lower() or "exists" in body.lower():
            return False
        raise SystemExit(f"Sign-up failed for {email}: {e.code} {body[:200]}") from e


async def user_id(db, email: str) -> str:
    found = await db.scalar(
        text('SELECT id FROM better_auth."user" WHERE lower(email) = lower(:e)'), {"e": email}
    )
    if not found:
        raise SystemExit(
            f"No account for {email}: is the web app at --web the one on this database?"
        )
    return found


async def reset(db) -> None:
    slugs = [n["slug"] for n in NEWSROOMS]
    ids = list(await db.scalars(select(Workspace.id).where(Workspace.slug.in_(slugs))))
    if ids:
        await db.execute(delete(Source).where(Source.workspace_id.in_(ids)))
        await db.execute(delete(Workspace).where(Workspace.id.in_(ids)))
        await db.commit()
        print(f"Removed {len(ids)} seeded newsroom(s).")


async def main(args) -> None:
    accounts: list[str] = []
    out = Path(args.accounts).expanduser()
    # Passwords from an earlier run, for accounts that already exist (sign-up cannot reset them).
    known = {}
    if out.exists():
        for line in out.read_text().splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) == 4 and parts[3].startswith("Checky-"):
                known[parts[2]] = parts[3]
    async with SessionLocal() as db:
        if args.reset:
            await reset(db)
        existing = set(await db.scalars(select(Workspace.slug)))
        users: dict[str, list[tuple[str, str]]] = {}
        for n in NEWSROOMS:
            people = []
            for name, email in n["people"]:
                password = "Checky-" + secrets.token_urlsafe(12)
                created = sign_up(args.web, name, email, password)
                shown = (
                    password
                    if created
                    else known.get(email, "(existing account: password unchanged)")
                )
                accounts.append(f"{n['name']}\t{name}\t{email}\t{shown}")
                people.append((await user_id(db, email), name))
            users[n["slug"]] = people

        spaces: dict[str, Workspace] = {}
        for n in NEWSROOMS:
            if n["slug"] in existing:
                raise SystemExit(f"{n['slug']} already exists: run with --reset to rebuild it.")
            ws = Workspace(
                name=n["name"],
                slug=n["slug"],
                settings=n["settings"],
                is_public=True,
                verification="approved",
                created_at=at("2017-09-01"),
            )
            db.add(ws)
            await db.flush()
            for uid, _ in users[n["slug"]]:
                db.add(Membership(workspace_id=ws.id, user_id=uid))
                db.add(
                    MemberPref(
                        workspace_id=ws.id,
                        user_id=uid,
                        beats=n["settings"]["beats"],
                        regions=n["regions"],
                    )
                )
            spaces[n["slug"]] = ws
        await db.commit()

        sources: list[tuple[Source, str]] = []
        to_analyze: list[Item] = []
        for d in sorted(DOSSIERS, key=lambda d: d["seen"]):
            ws, people = spaces[d["ws"]], users[d["ws"]]
            author = people[d["by"]][0]
            item = Item(
                workspace_id=ws.id,
                author_id=author,
                type="claim",
                title=d["title"],
                status=d["status"],
                tags=d["tags"],
                created_at=d["seen"],
                updated_at=d["seen"],
                data={
                    "ref": await next_ref(db, ws.id),
                    "first_seen_at": d["seen"].isoformat(),
                    "origin": d["origin"],
                    "location": d["place"],
                    "source_count": len(d["sources"]),
                    "assignee_id": people[d["assignee"]][0] if "assignee" in d else None,
                },
            )
            db.add(item)
            await db.flush()
            log(db, ws.id, author, item.id, "create", d["seen"])
            if d.get("verdict"):
                signer_id, signer = people[d["by"]]
                when = (d["seen"] + timedelta(hours=d.get("signed_after", 12))).isoformat()
                data = {
                    **item.data,
                    "verdict": d["verdict"],
                    "reason": d["reason"],
                    "signed_by": signer_id,
                    "signed_at": when,
                    "byline": {"newsroom": ws.name, "journalist": signer, "signed_at": when},
                    "published_by": signer_id,
                    "published_at": when,
                }
                data["signed_digest"] = signing.digest(item.title, item.body, data)
                item.data = data
                item.updated_at = datetime.fromisoformat(when)
                log(
                    db,
                    ws.id,
                    signer_id,
                    item.id,
                    "sign",
                    datetime.fromisoformat(when),
                    {"verdict": d["verdict"], "status": "published"},
                )
            for url, title, note in d["sources"]:
                s = Source(
                    workspace_id=ws.id,
                    item_id=item.id,
                    created_by=author,
                    kind="url",
                    status="queued",
                    url=url,
                    title=title,
                    created_at=d["seen"] + timedelta(minutes=40),
                )
                db.add(s)
                await db.flush()
                sources.append((s, note))
            for who, body, hours in d.get("comments", []):
                db.add(
                    Comment(
                        item_id=item.id,
                        author_id=people[who][0],
                        body=body,
                        created_at=d["seen"] + timedelta(hours=hours),
                    )
                )
            if d.get("analyze"):
                to_analyze.append(item)
        for tip in TIPS:
            ws = spaces[tip["ws"]]
            item = Item(
                workspace_id=ws.id,
                author_id="public",
                type="claim",
                title=tip["text"].splitlines()[0][:300],
                body=tip["text"],
                status="to_check",
                tags=["signalement"],
                created_at=tip["seen"],
                updated_at=tip["seen"],
                data={
                    "ref": await next_ref(db, ws.id),
                    "first_seen_at": tip["seen"].isoformat(),
                    "origin": tip["origin"],
                    "location": tip["place"],
                    "source_count": 0,
                    "public_tip": True,
                    "tip_token": secrets.token_urlsafe(18),
                },
            )
            db.add(item)
            await db.flush()
            log(db, ws.id, "public", item.id, "create", tip["seen"])
        await db.commit()

        for s, _ in sources:
            await enqueue(db, s.workspace_id, s.created_by, "ingest_url", {"source_id": str(s.id)})
        print(
            f"{len(DOSSIERS)} dossiers, {len(TIPS)} tips, {len(sources)} links queued for reading."
        )

        if args.no_wait:
            for item in to_analyze:
                await enqueue(
                    db,
                    item.workspace_id,
                    item.author_id,
                    "analyze_claim",
                    {"item_id": str(item.id)},
                )
        else:
            await finish(db, sources, to_analyze, args.wait)

    out.write_text("newsroom\tname\temail\tpassword\n" + "\n".join(accounts) + "\n")
    out.chmod(0o600)
    print(f"Accounts written to {out} (keep it private).")


async def finish(db, sources, to_analyze, minutes: int) -> None:
    """Wait for the API's workers to read the links; a page that refused keeps the note instead."""
    links = [
        (s.id, s.workspace_id, s.created_by, note, NOTE_DATES.get(s.url)) for s, note in sources
    ]
    claims = [(i.id, i.workspace_id, i.author_id) for i in to_analyze]
    ids = [x[0] for x in links]
    deadline = datetime.now(UTC) + timedelta(minutes=minutes)
    while datetime.now(UTC) < deadline:
        pending = await db.scalar(
            select(func.count())
            .select_from(Source)
            .where(Source.id.in_(ids), Source.status.in_(["queued", "processing"]))
        )
        if not pending:
            break
        print(f"  {pending} link(s) still being read…")
        await asyncio.sleep(10)
    from app.modules.rag import queue_embedding

    db.expire_all()
    rescued = 0
    for source_id, ws, by, note, day in links:
        fresh = await db.get(Source, source_id)
        if fresh.status == "ready" and fresh.text.strip():
            continue
        fresh.text = note
        fresh.published_at = fresh.published_at or day
        fresh.status = "ready"
        fresh.error = None
        rescued += 1
        await db.commit()
        await queue_embedding(db, ws, by, source_id)
    print(f"{len(links) - rescued} link(s) read, {rescued} kept the journalist's note.")
    for item_id, ws, by in claims:
        await enqueue(db, ws, by, "analyze_claim", {"item_id": str(item_id)})
    print(f"{len(claims)} analyses queued.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--web", default="http://localhost:3000", help="the web app on the same database"
    )
    p.add_argument(
        "--accounts", default="~/checky-seed-accounts.txt", help="where to write the passwords"
    )
    p.add_argument("--reset", action="store_true", help="delete the seeded newsrooms first")
    p.add_argument("--no-wait", action="store_true", help="do not wait for the links to be read")
    p.add_argument("--wait", type=int, default=6, help="minutes to wait for the links (default 6)")
    asyncio.run(main(p.parse_args()))
