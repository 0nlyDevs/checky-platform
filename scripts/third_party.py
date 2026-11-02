"""Write THIRD_PARTY.md: every direct dependency with its version and license (hackathon rules, article 6).

Run with the API's environment so Python package metadata is available:
    uv run --project apps/api python scripts/third_party.py
"""

import json
import re
import sys
import tomllib
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Services and APIs are not packages; keep this list in sync with docs/PRD.md.
SERVICES = [
    ("Neon (Postgres, pgvector, Object Storage)", "Hosted service, free plan", "https://neon.com/terms-of-service"),
    ("Vercel (web hosting)", "Hosted service, Hobby plan", "https://vercel.com/legal/terms"),
    ("Render (API hosting)", "Hosted service, free plan", "https://render.com/terms"),
    ("Groq API (LLM, Whisper)", "Hosted API, free tier", "https://groq.com/terms-of-use/"),
    ("Google Gemini API", "Hosted API, free tier", "https://ai.google.dev/gemini-api/terms"),
    ("NVIDIA NIM API", "Hosted API, free tier", "https://www.nvidia.com/en-us/agreements/"),
    ("Anthropic Claude API (optional provider, off without a key)", "Hosted API, paid", "https://www.anthropic.com/legal/commercial-terms"),
    ("ElevenLabs API (assistant voice, optional)", "Hosted API, free plan", "https://elevenlabs.io/terms-of-use"),
    ("DuckDuckGo HTML search (agent web search, no key)", "Public web page", "https://duckduckgo.com/terms"),
    ("Tavily Search API (optional dedicated web search)", "Hosted API; Researcher free plan only, basic search, no pay-as-you-go", "https://docs.tavily.com/documentation/api-credits"),
    ("Wikipedia / Wikimedia API (agent search; article text CC BY-SA)", "Public API, content CC BY-SA 4.0", "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use"),
    ("Google Fact Check Tools API (optional)", "Hosted API, free with a key", "https://developers.google.com/fact-check/tools/api"),
    ("Google Fonts: Archivo, Atkinson Hyperlegible Next (the app)", "SIL Open Font License 1.1", "https://fonts.google.com"),
    ("Google Fonts: Public Sans (pitch deck and video)", "SIL Open Font License 1.1", "https://fonts.google.com/specimen/Public+Sans"),
    ("Google Fonts: Anton (Vernon Adams), self-hosted (pitch deck and video)", "SIL Open Font License 1.1", "https://fonts.google.com/specimen/Anton"),
    ("Google Fonts: Special Elite (Astigmatic), self-hosted (pitch deck and video)", "Apache License 2.0", "https://fonts.google.com/specimen/Special+Elite"),
    ("Photographs of Antananarivo, Wikimedia Commons, halftoned (pitch deck)", "CC BY-SA 4.0, CC BY-SA 2.0, CC0", "apps/web/public/site/credits.json"),
]


def npm_direct() -> dict[str, set[str]]:
    """Direct dependencies of each npm workspace, and which workspace uses them."""
    used: dict[str, set[str]] = {}
    for pkg in [ROOT / "package.json", *ROOT.glob("apps/*/package.json"), *ROOT.glob("packages/*/package.json")]:
        data = json.loads(pkg.read_text())
        where = pkg.parent.relative_to(ROOT).as_posix() or "root"
        where = "root" if where == "." else where
        for section in ("dependencies", "devDependencies"):
            for name in data.get(section, {}):
                if not name.startswith("@fanilo/"):
                    used.setdefault(name, set()).add(where)
    return used


def npm_meta(name: str) -> tuple[str, str]:
    for base in (ROOT / "node_modules", ROOT / "apps/web/node_modules"):
        f = base / name / "package.json"
        if f.exists():
            d = json.loads(f.read_text())
            lic = d.get("license") or (d.get("licenses") or [{}])[0].get("type") or "UNKNOWN"
            return d.get("version", "?"), lic if isinstance(lic, str) else lic.get("type", "UNKNOWN")
    return "not installed", "UNKNOWN"


def python_direct() -> list[str]:
    py = tomllib.loads((ROOT / "apps/api/pyproject.toml").read_text())
    reqs = py["project"]["dependencies"] + py.get("dependency-groups", {}).get("dev", [])
    return sorted({re.split(r"[\[<>=~! ]", r, maxsplit=1)[0] for r in reqs}, key=str.lower)


def python_meta(name: str) -> tuple[str, str]:
    try:
        m = metadata.metadata(name)
    except metadata.PackageNotFoundError:
        return "not installed", "UNKNOWN"
    lic = m.get("License-Expression") or ""
    if not lic:
        classifiers = [c.split("::")[-1].strip() for c in m.get_all("Classifier") or [] if c.startswith("License ::")]
        lic = ", ".join(classifiers) or (m.get("License") or "").splitlines()[0] if (classifiers or m.get("License")) else ""
    return m["Version"], (lic or "UNKNOWN").strip()


def main() -> int:
    lines = [
        "# Third-party components",
        "",
        "Every library, runtime, font and API this project uses, with its version and license,",
        "as required by article 6 of the FANILO Hackathon rules. Direct dependencies are listed;",
        "their own dependencies are pinned in `package-lock.json` and `apps/api/uv.lock`.",
        "",
        "Generated by `npm run third-party`. Do not edit by hand.",
        "",
        "## Runtimes",
        "",
        "| Component | Version | License |",
        "| --- | --- | --- |",
        f"| Python | {(ROOT / 'apps/api/.python-version').read_text().strip()} | PSF-2.0 |",
        "| Node.js | see `.github/workflows/ci.yml` | MIT |",
        "",
        "## JavaScript packages (npm)",
        "",
        "| Package | Version | License | Used in |",
        "| --- | --- | --- | --- |",
    ]
    unknown = []
    for name, where in sorted(npm_direct().items(), key=lambda kv: kv[0].lower()):
        version, lic = npm_meta(name)
        if lic == "UNKNOWN":
            unknown.append(name)
        lines.append(f"| `{name}` | {version} | {lic} | {', '.join(sorted(where))} |")
    lines += ["", "## Python packages (apps/api)", "", "| Package | Version | License |", "| --- | --- | --- |"]
    for name in python_direct():
        version, lic = python_meta(name)
        if lic == "UNKNOWN":
            unknown.append(name)
        lines.append(f"| `{name}` | {version} | {lic} |")
    lines += ["", "## Services, APIs and fonts", "", "| Component | Terms | Link |", "| --- | --- | --- |"]
    lines += [f"| {n} | {terms} | {url} |" for n, terms, url in SERVICES]
    (ROOT / "THIRD_PARTY.md").write_text("\n".join(lines) + "\n")
    print(f"wrote THIRD_PARTY.md{'; license unknown for: ' + ', '.join(unknown) if unknown else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
