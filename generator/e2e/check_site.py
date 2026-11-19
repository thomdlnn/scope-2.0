"""Vérification du site SCOPE dans un navigateur headless (Playwright).

Lancé par scripts/verifier-site.sh dans l'image Docker Playwright, pendant que
le générateur tourne en boucle sur une fausse racine :
  python check_site.py <url_de_base> <racine> <dossier_captures>
Vérifie l'accueil et la page du projet « demo » (ordinateur et mobile, clair et
sombre), puis la mise à jour en direct : un rapport modifié sur le disque
apparaît sans recharger, filtres et sections dépliées conservés.
"""

import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE, RACINE, SHOTS = sys.argv[1].rstrip("/"), Path(sys.argv[2]), sys.argv[3]
VIEWPORTS = {
    "desktop": dict(viewport={"width": 1280, "height": 900}),
    "mobile": dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True),
}
errors: list[str] = []


def no_horizontal_scroll(page, label):
    w = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    assert w[0] <= w[1], f"{label} : défilement horizontal ({w[0]}px > {w[1]}px)"


def watch(page, label):
    page.on("pageerror", lambda exc: errors.append(f"{label} : {exc}"))
    page.on("dialog", lambda d: errors.append(f"{label} : dialogue JS inattendu (XSS ?) {d.message}"))
    page.on("console", lambda m: m.type == "error" and errors.append(f"{label} : console : {m.text}"))


with sync_playwright() as p:
    browser = p.chromium.launch()
    for vp_name, vp in VIEWPORTS.items():
        for scheme in ("light", "dark"):
            label = f"{vp_name}-{scheme}"
            ctx = browser.new_context(color_scheme=scheme, locale="fr-FR", timezone_id="Europe/Paris", **vp)
            page = ctx.new_page()
            watch(page, label)

            # Accueil : compte des attentes, puis un bloc par projet.
            page.goto(f"{BASE}/")
            expect(page.locator("#attente")).to_contain_text("2 actions en attente")
            expect(page.locator(".projet-bloc")).to_have_count(2)
            demo = page.locator("#projet-demo")
            expect(demo.locator(".projet-entete")).to_contain_text("1 action en attente")
            attente = demo.locator("#attente-demo")
            expect(attente.locator(".pt-question").first).to_contain_text("quel Client ID Google")
            expect(attente).to_contain_text("Page de login avec authentification Google")
            expect(demo.locator("#en-cours-demo .silence")).to_have_count(1)
            expect(demo.locator("#recentes-demo > summary")).to_contain_text("7 derniers jours")
            expect(page.locator("#age")).to_contain_text("En direct")
            expect(page.locator(".error-box")).to_contain_text("casse.yml")  # réglage invalide signalé
            expect(demo.locator(".projet-entete")).to_contain_text("2 PR ouverte(s)")
            expect(page.locator(".tagline")).to_contain_text("La supervision de vos agents IA")
            no_horizontal_scroll(page, f"{label} accueil")
            page.screenshot(path=f"{SHOTS}/accueil-{label}.png", full_page=True)

            # Page projet.
            page.get_by_role("link", name="demo", exact=True).click()
            expect(page.locator("h1")).to_have_text("demo")
            expect(page.locator("#main .demande")).to_have_count(10)
            expect(page.locator("#count")).to_have_text("10 demande(s)")
            expect(page.locator(".action.a-deploy")).to_have_count(1)
            expect(page.locator("#illisibles .demande")).to_have_count(2)
            # Panneau des dépôts (token) et santé appelée par le navigateur.
            expect(page.locator("#health a")).to_have_text("Dégradé · 1/2 services")
            expect(page.locator(".kpis")).to_contain_text("PR ouvertes")
            if vp_name == "mobile":
                page.locator("#sidebar-toggle").click()  # replié par défaut sur mobile
            sidebar = page.locator("#sidebar")
            expect(sidebar).to_contain_text("#12 Page de login Google")
            expect(sidebar).to_contain_text("PR non lues")
            expect(sidebar).to_contain_text("2 commit(s) à déployer")
            expect(page.locator('.repo-card[data-repo-name="demo-api"] .live')).to_contain_text("= dernier commit")
            sidebar.locator('[data-filtre-depot="demo-front"]').click()
            expect(page.locator("#count")).to_have_text("5 demande(s)")
            sidebar.locator('[data-filtre-depot="demo-front"]').click()
            page.select_option("select[name=depot]", "demo-api")
            expect(page.locator("#count")).to_have_text("5 demande(s)")
            assert "depot=demo-api" in page.url
            expect(page.locator("#attente")).to_be_hidden()  # aucune attente côté demo-api
            page.select_option("select[name=depot]", "")
            no_horizontal_scroll(page, f"{label} projet")
            page.screenshot(path=f"{SHOTS}/projet-{label}.png", full_page=True)
            ctx.close()

    # Mise à jour en direct : filtres et sections dépliées conservés.
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, locale="fr-FR")
    page = ctx.new_page()
    watch(page, "direct")
    page.goto(f"{BASE}/demo/#depot=demo-api")
    expect(page.locator("#count")).to_have_text("5 demande(s)")
    carte = page.locator(".demande", has_text="Add rate limiting")
    carte.locator("summary").click()
    detail_id = carte.locator("details").get_attribute("id")
    expect(page.locator(f"#{detail_id}")).to_have_attribute("open", "")

    f = next((RACINE / "demo" / "demo-api" / ".scope" / "rapports").glob("*rate-limit.md"))
    f.write_text(
        f.read_text()
        .replace("status: in-progress", "status: waiting")
        .replace("- Note: the limit", "- Question: is 100 per minute OK?\n- Note: the limit"),
        encoding="utf-8",
    )
    expect(page.locator("#attente .demande", has_text="Add rate limiting")).to_be_visible(timeout=15000)
    expect(page.locator(f"#{detail_id}")).to_have_attribute("open", "")
    expect(page.locator("select[name=depot]")).to_have_value("demo-api")
    expect(page.locator("#count")).to_have_text("5 demande(s)")
    expect(page.locator("#attente .pt-question", has_text="is 100 per minute OK?")).to_be_visible()
    expect(page.locator("#attente .demande", has_text="Client ID")).to_be_hidden()  # filtre demo-api
    expect(page.locator("#health a")).to_have_text("Dégradé · 1/2 services")  # santé réappliquée
    page.screenshot(path=f"{SHOTS}/direct.png", full_page=True)
    browser.close()

if errors:
    print("\n".join(errors))
    sys.exit(1)
print("vérification navigateur : OK")
