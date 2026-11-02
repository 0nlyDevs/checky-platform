"""Film the demo video from docs/pitch/video/scenes.json.

Each scene is a chapter card (drawn in the dossier world) followed by a recording of the real app
driven by Playwright: a visible cursor moves, clicks and types like a person. Scenes are cut
together into one silent 1080p mp4 to be commented live, or narrated afterwards in any editor.

    uv run --with playwright python -I scripts/pitch_video.py              # sign up a throwaway account, film everything
    uv run --with playwright python -I scripts/pitch_video.py --only dossier verdict   # re-shoot two scenes
    uv run --with playwright python -I scripts/pitch_video.py --email me@x --password ...   # an existing account

Needs the web app and the API running (defaults to http://localhost:3000; --base-url for the
deployed app), ffmpeg, and the Playwright chromium in ~/.cache/ms-playwright. Output goes to
docs/pitch/video/out/ (gitignored): demo.mp4, and scenes/<id>.mp4 for each scene.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "docs" / "pitch" / "video"
OUT = KIT / "out"
FONTS = ROOT / "apps" / "web" / "app" / "fonts"
SIZE = {"width": 1920, "height": 1080}
FPS = 30

# The dossier palette, as on the public pages.
MANILA, MANILA_DEEP, CARD, INK, ALARM = "#dcc9a3", "#cfb98f", "#efe4c8", "#141210", "#c42a20"

CSS = f"""
@font-face {{ font-family: Anton; src: url("file://{FONTS}/Anton-400.woff2") format("woff2"); }}
@font-face {{ font-family: Typed; src: url("file://{FONTS}/SpecialElite-400.woff2") format("woff2"); }}
@import url("https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600&display=swap");
* {{ box-sizing: border-box; margin: 0; }}
html, body {{ width: 1920px; height: 1080px; overflow: hidden; }}
body {{ background: {MANILA}; color: {INK}; font-family: "Public Sans", system-ui, sans-serif; }}
.anton {{ font-family: Anton, "Arial Narrow", sans-serif; text-transform: uppercase; }}
.typed {{ font-family: Typed, "Courier New", monospace; }}
"""

CHAPTER_HTML = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><style>{css}
.card {{ position: absolute; left: 120px; top: 140px; width: 1680px; height: 800px; background: {CARD};
  box-shadow: 0 10px 30px rgba(20,18,16,.22); transform: rotate(-.5deg); padding: 70px 90px; }}
.tab {{ display: inline-block; background: {INK}; color: {MANILA}; font-size: 30px; letter-spacing: .16em; padding: 14px 34px 10px;
  clip-path: polygon(0 100%, 7% 0, 93% 0, 100% 100%); }}
h1 {{ font-size: 150px; line-height: .92; margin-top: 60px; max-width: 1450px; }}
.cap {{ font-size: 34px; margin-top: 54px; max-width: 1300px; line-height: 1.35; }}
.foot {{ position: absolute; left: 120px; bottom: 60px; font-size: 26px; }}
.rec {{ position: absolute; right: 120px; bottom: 60px; font-size: 26px; }}
.rec::before {{ content: ""; display: inline-block; width: 16px; height: 16px; border-radius: 50%; background: {ALARM}; margin-right: 12px; }}
</style></head><body>
<div class="card"><span class="tab anton">{tab}</span><h1 class="anton">{title}</h1><p class="cap">{caption}</p></div>
<p class="foot typed">{foot}</p><p class="rec typed">REC · {clock}</p>
</body></html>"""

CAPTION_HTML = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><style>{css}
html, body {{ background: transparent; height: 220px; }}
.strip {{ position: absolute; left: 50%; bottom: 24px; transform: translateX(-50%) rotate(-.3deg); width: 1500px; background: {CARD};
  box-shadow: 0 8px 24px rgba(20,18,16,.28); padding: 24px 44px 26px; display: flex; gap: 34px; align-items: baseline; }}
.n {{ font-size: 24px; white-space: nowrap; }}
.t {{ font-size: 36px; line-height: 1.3; font-weight: 500; }}
</style></head><body><div class="strip"><span class="n typed">{tab}</span><span class="t">{text}</span></div></body></html>"""

CURSOR_JS = """
(() => {
  const c = document.createElement('div');
  Object.assign(c.style, { position: 'fixed', left: '-100px', top: '-100px', width: '26px', height: '26px', border: '3px solid #141210',
    borderRadius: '50%', background: 'rgba(239,228,200,.75)', pointerEvents: 'none', zIndex: '2147483647',
    transform: 'translate(-50%,-50%)', transition: 'width .1s, height .1s, background-color .1s', boxShadow: '0 2px 8px rgba(20,18,16,.35)' });
  // The dev server's "N" badge and its "Rendering" toasts live in <nextjs-portal>: keep them off camera.
  const hide = document.createElement('style');
  hide.textContent = 'nextjs-portal { display: none !important; }';
  const add = () => { document.documentElement.appendChild(c); document.head.appendChild(hide); };
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', add) : add();
  window.addEventListener('mousemove', (e) => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
  window.addEventListener('mousedown', () => { c.style.width = '40px'; c.style.height = '40px'; c.style.background = 'rgba(196,42,32,.45)'; }, true);
  window.addEventListener('mouseup', () => { c.style.width = '26px'; c.style.height = '26px'; c.style.background = 'rgba(239,228,200,.75)'; }, true);
})();
"""


def chapter_card(tab: str, title: str, caption: str, clock: float, foot: str) -> str:
    return CHAPTER_HTML.format(
        css=CSS,
        CARD=CARD,
        INK=INK,
        MANILA=MANILA,
        ALARM=ALARM,
        tab=html.escape(tab),
        title=html.escape(title),
        caption=html.escape(caption),
        foot=html.escape(foot),
        clock=time.strftime("%H:%M:%S", time.gmtime(clock)),
    )


def caption_strip(tab: str, text: str) -> str:
    return CAPTION_HTML.format(css=CSS, CARD=CARD, tab=html.escape(tab), text=html.escape(text))


def chromium() -> str:
    found = sorted(
        (Path.home() / ".cache" / "ms-playwright").glob("chromium-*/chrome-linux*/chrome")
    )
    if not found:
        sys.exit(
            "Playwright chromium not found in ~/.cache/ms-playwright (run: npx playwright install chromium)"
        )
    return str(found[-1])


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


class Camera:
    """Renders the cards in a headless page and turns everything into same-shaped mp4 clips."""

    def __init__(self, pw, tmp: Path):
        self.browser = pw.chromium.launch(executable_path=chromium())
        self.tmp = tmp

    def shot(self, name: str, markup: str, height: int, transparent: bool) -> Path:
        src = self.tmp / f"{name}.html"
        src.write_text(markup, encoding="utf-8")
        page = self.browser.new_page(viewport={"width": SIZE["width"], "height": height})
        page.goto(src.as_uri())
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(300)
        png = self.tmp / f"{name}.png"
        page.screenshot(path=str(png), omit_background=transparent)
        page.close()
        return png

    def still(self, png: Path, seconds: float, out: Path) -> Path:
        run(
            [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-t",
                str(seconds),
                "-i",
                str(png),
                "-vf",
                f"fps={FPS},format=yuv420p",
                "-c:v",
                "libx264",
                "-crf",
                "20",
                "-preset",
                "veryfast",
                str(out),
            ]
        )
        return out

    def clip(self, webm: Path, caption: Path | None, trim: float, out: Path) -> Path:
        if caption:
            graph = f"[0:v]scale={SIZE['width']}:{SIZE['height']},fps={FPS}[v];[v][1:v]overlay=0:H-h:format=auto,format=yuv420p"
            inputs = [
                "-ss",
                str(trim),
                "-i",
                str(webm),
                "-i",
                str(caption),
                "-filter_complex",
                graph,
            ]
        else:
            inputs = [
                "-ss",
                str(trim),
                "-i",
                str(webm),
                "-vf",
                f"scale={SIZE['width']}:{SIZE['height']},fps={FPS},format=yuv420p",
            ]
        run(
            [
                "ffmpeg",
                "-y",
                *inputs,
                "-c:v",
                "libx264",
                "-crf",
                "20",
                "-preset",
                "veryfast",
                str(out),
            ]
        )
        return out

    def concat(self, clips: list[Path], out: Path) -> None:
        lst = self.tmp / "concat.txt"
        lst.write_text("".join(f"file '{c}'\n" for c in clips))
        run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(lst),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(out),
            ]
        )


class Hand:
    """Moves a visible cursor and types like a person, so the recording shows what happens."""

    def __init__(self, page: Page):
        self.page = page
        self.x, self.y = 960, 540

    def move_to(self, x: float, y: float) -> None:
        self.page.mouse.move(self.x, self.y)
        steps = max(12, int(((x - self.x) ** 2 + (y - self.y) ** 2) ** 0.5 / 40))
        self.page.mouse.move(x, y, steps=steps)
        self.x, self.y = x, y

    def target(self, selector: str):
        loc = self.page.locator(selector).first
        loc.wait_for(state="visible", timeout=15000)
        loc.scroll_into_view_if_needed()
        self.page.wait_for_timeout(250)
        box = loc.bounding_box()
        if not box:
            raise RuntimeError(f"{selector}: no box")
        return loc, box["x"] + box["width"] / 2, box["y"] + min(box["height"] / 2, 24)

    def hover(self, selector: str) -> None:
        _, x, y = self.target(selector)
        self.move_to(x, y)

    def click(self, selector: str) -> None:
        self.hover(selector)
        self.page.wait_for_timeout(180)
        self.page.mouse.down()
        self.page.wait_for_timeout(90)
        self.page.mouse.up()

    def type(self, selector: str, text: str) -> None:
        self.click(selector)
        self.page.wait_for_timeout(200)
        self.page.keyboard.type(text, delay=38)

    def scroll(self, dy: int) -> None:
        for _ in range(abs(dy) // 100):
            self.page.mouse.wheel(0, 100 if dy > 0 else -100)
            self.page.wait_for_timeout(45)


def wait_ready(page: Page, hand: Hand, selector: str, timeout: int) -> None:
    """Waits for the page's content (the dev server and a sleepy API can take seconds); a failed
    load shows « Réessayer », which the hand clicks like anyone would."""
    deadline = time.monotonic() + timeout / 1000
    retry = page.get_by_role("button", name="Réessayer")
    while time.monotonic() < deadline:
        if page.locator(selector).first.is_visible():
            return
        if retry.first.is_visible():
            print("    (the page failed to load; clicking Réessayer)")
            hand.click("role=button[name='Réessayer']")
            page.wait_for_timeout(1500)
        page.wait_for_timeout(250)
    raise TimeoutError(f"{selector} never showed up")


class Api:
    """Prepares the demo between scenes through the API, as the signed-in user: finds a claim by
    its title, edits it, runs its analysis. Found ids are kept as {names} usable in paths."""

    def __init__(self, pw, base: str, api: str, state: dict, ws: str):
        self.web = pw.request.new_context(base_url=base, storage_state=state)
        self.root = f"{api.rstrip('/')}/api/v1/workspaces/{ws}"
        self.vars = {"ws": ws}

    def fill(self, text: str) -> str:
        for name, value in self.vars.items():
            text = text.replace("{" + name + "}", value)
        return text

    def call(self, method: str, path: str, body: dict | None = None):
        token = self.web.get("/api/auth/token").json()["token"]
        res = self.web.fetch(
            self.root + self.fill(path),
            method=method,
            headers={"Authorization": f"Bearer {token}"},
            data=body,
        )
        if not res.ok:
            raise RuntimeError(f"{method} {path}: {res.status} {res.text()[:200]}")
        return res.json() if res.body() else None

    def run(self, ops: list[dict]) -> None:
        for op in ops:
            if "find" in op:
                items = self.call("GET", f"/items?q={op['find']}&limit=1")["items"]
                if not items:
                    raise RuntimeError(f"no claim matches {op['find']!r}")
                self.vars[op.get("as", "claim")] = items[0]["id"]
            elif "patch" in op:
                self.call("PATCH", f"/items/{{{op['patch']}}}", op["body"])
            elif "analyze" in op:
                job = self.call("POST", f"/items/{{{op['analyze']}}}/analyze")
                self.wait_job(job["id"], op.get("timeout", 150))
            elif "wait_indexed" in op:
                self.wait_indexed(op["wait_indexed"], op.get("timeout", 180))
            else:
                raise ValueError(f"unknown setup step {op}")

    def wait_job(self, job_id: str, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.call("GET", f"/jobs/{job_id}")
            if job["status"] == "done":
                return
            if job["status"] == "failed":
                raise RuntimeError(f"job {job_id} failed: {job['error']}")
            time.sleep(2)
        raise TimeoutError(f"job {job_id} still running after {timeout} s")

    def wait_indexed(self, query: str, timeout: float) -> None:
        """The demo sources are embedded by background jobs right after the reset; nothing can be
        cited until they are done."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.call("POST", "/search", {"query": query, "k": 1}):
                return
            time.sleep(3)
        print("  (warning: no source is indexed yet; scenes that cite sources may show nothing)")


def play(page: Page, hand: Hand, steps: list[dict], base: str, api: Api) -> None:
    for step in steps:
        optional = step.get("optional", False)
        try:
            if "goto" in step:
                page.goto(base + api.fill(step["goto"]), wait_until="load")
                if step.get("ready"):
                    wait_ready(page, hand, step["ready"], step.get("timeout", 60000))
                page.wait_for_timeout(step.get("settle", 1200))
            elif "click" in step:
                hand.click(step["click"])
            elif "hover" in step:
                hand.hover(step["hover"])
            elif "type" in step:
                hand.type(step["type"][0], step["type"][1])
            elif "press" in step:
                page.keyboard.press(step["press"])
            elif "scroll" in step:
                hand.scroll(int(step["scroll"]))
            elif "wait_for" in step:
                page.locator(step["wait_for"]).first.wait_for(
                    state="visible", timeout=step.get("timeout", 90000)
                )
            elif "wait" in step:
                page.wait_for_timeout(int(step["wait"]))
            else:
                raise ValueError(f"unknown step {step}")
        except Exception as e:  # a missing optional element must not stop the shoot
            if not optional:
                raise
            print(f"    (skipped optional step {step}: {type(e).__name__})")


def warm_up(browser, state: dict, base: str, api: Api, scenes: list[dict]) -> None:
    """Opens every page the scenes visit once, off camera, so a dev server compiles them before
    the recording instead of during it."""
    ctx = browser.new_context(viewport=SIZE, storage_state=state)
    page = ctx.new_page()
    paths = dict.fromkeys(api.fill(s["goto"]) for sc in scenes for s in sc["steps"] if "goto" in s)
    for p in paths:
        page.goto(base + p, wait_until="load", timeout=120000)
        page.wait_for_timeout(1500)
    ctx.close()


def sign_in(pw, args, base: str) -> tuple[dict, str]:
    """Signs in (or signs up a throwaway with demo data) and returns the storage state and workspace id."""
    browser = pw.chromium.launch(executable_path=chromium())
    ctx = browser.new_context(viewport=SIZE)
    page = ctx.new_page()
    if args.email:
        page.goto(base + "/connexion")
        page.fill("#email", args.email)
        page.fill("#password", args.password)
        page.click("button[type=submit]")
    else:
        stamp = int(time.time())
        email, password = f"pitch-{stamp}@fanilo.test", f"Pitch-{stamp}-demo"
        print(f"  signing up {email} with the demo data")
        page.goto(base + "/inscription")
        page.fill("#name", args.name)
        page.fill("#email", email)
        page.fill("#password", password)
        page.click("button[type=submit]")
        page.wait_for_url(re.compile(r"/($|\?)"), timeout=30000)
        page.wait_for_selector("#ws-name", timeout=30000)
        page.fill("#ws-name", args.workspace)
        page.click("button[type=submit]")
    page.wait_for_url(re.compile(r"/w/[^/]+/"), timeout=90000)
    ws = re.search(r"/w/([^/]+)/", page.url).group(1)
    state = ctx.storage_state()
    ctx.close()
    browser.close()
    return state, ws


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--scenes", default=str(KIT / "scenes.json"))
    ap.add_argument("--base-url", default="http://localhost:3000")
    ap.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="the API, for the setup steps that prepare the demo between scenes",
    )
    ap.add_argument("--email")
    ap.add_argument("--password")
    ap.add_argument("--name", default="Ravo Rakoto", help="display name of the throwaway account")
    ap.add_argument(
        "--workspace", default="Desk du matin", help="newsroom name of the throwaway workspace"
    )
    ap.add_argument(
        "--only", nargs="*", help="scene ids to re-shoot; the others are reused from out/scenes"
    )
    ap.add_argument("--headed", action="store_true", help="watch the browser while it films")
    args = ap.parse_args()
    if bool(args.email) != bool(args.password):
        ap.error("--email and --password go together")

    spec = json.loads(Path(args.scenes).read_text(encoding="utf-8"))
    base = args.base_url.rstrip("/")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "scenes").mkdir(exist_ok=True)
    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg is required")

    with sync_playwright() as pw, tempfile.TemporaryDirectory(prefix="pitch-") as tmpdir:
        tmp = Path(tmpdir)
        cam = Camera(pw, tmp)
        state, ws = sign_in(pw, args, base)
        print(f"  workspace {ws}")
        api = Api(pw, base, args.api_url, state, ws)
        api.run(spec.get("setup", []))
        browser = pw.chromium.launch(executable_path=chromium(), headless=not args.headed)
        warm_up(browser, state, base, api, spec["scenes"])

        clips: list[Path] = []
        foot = spec.get("footer", "FANILO · démo")
        clock = 0.0

        def still_card(name: str, card: dict, default_tab: str, seconds: float) -> Path:
            markup = chapter_card(
                card.get("tab", default_tab),
                card.get("title", ""),
                card.get("caption", ""),
                clock,
                foot,
            )
            png = cam.shot(name, markup, SIZE["height"], False)
            return cam.still(png, card.get("seconds", seconds), tmp / f"{name}.mp4")

        clips.append(still_card("title", spec.get("title", {}), "Démo", 2.2))
        for n, scene in enumerate(spec["scenes"], 1):
            sid = scene["id"]
            final = OUT / "scenes" / f"{sid}.mp4"
            tab = f"{n} · {scene['chapter']}"
            api.run(
                scene.get("before", [])
            )  # also for kept scenes, so the demo moves on the same way
            if args.only and sid not in args.only and final.exists():
                print(f"  {sid}: kept")
                clips.append(final)
                continue
            print(f"  {sid}: filming")
            caption = scene.get("caption", "")
            card_png = cam.shot(
                f"card-{sid}",
                chapter_card(tab, scene["title"], caption, clock, foot),
                SIZE["height"],
                False,
            )
            cap_png = (
                cam.shot(f"cap-{sid}", caption_strip(tab, caption), 220, True) if caption else None
            )

            ctx = browser.new_context(
                viewport=SIZE,
                storage_state=state,
                record_video_dir=str(tmp / "rec"),
                record_video_size=SIZE,
                locale="fr-FR",
                color_scheme="light",
            )
            ctx.add_init_script(CURSOR_JS)
            page = ctx.new_page()
            started = time.monotonic()
            try:
                play(page, Hand(page), scene["steps"], base, api)
            except Exception:
                page.screenshot(path=str(OUT / f"failed-{sid}.png"))
                print(f"  {sid}: failed, see {OUT / f'failed-{sid}.png'}")
                raise
            page.wait_for_timeout(int(scene.get("hold", 1500)))
            clock += time.monotonic() - started
            video = page.video
            page.close()
            ctx.close()
            webm = tmp / f"{sid}.webm"
            video.save_as(str(webm))

            card_clip = cam.still(card_png, scene.get("card_seconds", 1.6), tmp / f"card-{sid}.mp4")
            scene_clip = cam.clip(webm, cap_png, scene.get("trim", 0.4), tmp / f"scene-{sid}.mp4")
            cam.concat([card_clip, scene_clip], final)
            clips.append(final)

        clips.append(still_card("end", spec.get("end", {}), "Fin", 2.5))

        browser.close()
        out = OUT / "demo.mp4"
        cam.concat(clips, out)
        probe = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(out),
        ]
        seconds = float(subprocess.run(probe, capture_output=True, text=True, check=True).stdout)
        print(f"wrote {out} ({seconds:.0f} s, {len(spec['scenes'])} scenes)")


if __name__ == "__main__":
    main()
