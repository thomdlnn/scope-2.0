"""Vérification du site généré dans un navigateur headless (Playwright).

Lancé par scripts/verifier-site.sh dans l'image Docker Playwright :
  python check_site.py <url_de_base> <dossier_captures>
Vérifie l'accueil et la page du projet « demo », sur ordinateur et sur mobile,
et enregistre des captures d'écran.
"""

import re
import sys

from playwright.sync_api import expect, sync_playwright

BASE, SHOTS = sys.argv[1].rstrip("/"), sys.argv[2]
VIEWPORTS = {
    "desktop": dict(viewport={"width": 1280, "height": 900}),
    "mobile": dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True),
}
SCHEMES = ("light", "dark")
errors: list[str] = []


def no_horizontal_scroll(page, label):
    w = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    assert w[0] <= w[1], f"{label} : défilement horizontal ({w[0]}px > {w[1]}px)"


with sync_playwright() as p:
    browser = p.chromium.launch()
    for vp_name, vp in VIEWPORTS.items():
        for scheme in SCHEMES:
            label = f"{vp_name}-{scheme}"
            ctx = browser.new_context(color_scheme=scheme, locale="fr-FR", timezone_id="Europe/Paris", **vp)
            page = ctx.new_page()
            page.on("pageerror", lambda exc, l=label: errors.append(f"{l} : {exc}"))
            page.on("dialog", lambda d, l=label: errors.append(f"{l} : dialogue JS inattendu (XSS ?) {d.message}"))

            # Accueil
            page.goto(f"{BASE}/")
            expect(page.locator("h1")).to_have_text("Projets")
            expect(page.locator(".projects .card")).to_have_count(2)
            refresh = page.get_by_role("link", name="Actualiser")
            expect(refresh).to_be_visible()
            expect(page.locator(".top .age")).to_contain_text("Mis à jour")
            expect(page.get_by_role("link", name="Démo")).to_be_visible()
            no_horizontal_scroll(page, f"{label} accueil")
            page.screenshot(path=f"{SHOTS}/accueil-{label}.png", full_page=True)

            # Page projet
            page.get_by_role("link", name="Démo").click()
            expect(page.locator("h1")).to_have_text("Démo")
            # Bandeau du projet : indicateurs + santé appelée par le navigateur
            kpis = page.locator(".project-head .kpis")
            expect(kpis).to_contain_text("Dernier prompt")
            expect(kpis).to_contain_text("À déployer")
            expect(page.locator("#health a")).to_have_text("Dégradé · 1/2 services")
            expect(page.locator("#health a")).to_have_attribute("title", re.compile("demo-api : unavailable"))
            reports = page.locator("#feed .report")
            expect(reports).to_have_count(7)
            expect(page.locator("#count")).to_have_text("7 rapport(s)")
            expect(page.locator(".report.invalid")).to_have_count(2)
            expect(page.locator(".next").first).to_be_visible()
            expect(page.locator("script", has_text="xss")).to_have_count(0)
            no_horizontal_scroll(page, f"{label} projet")

            # Panneau des dépôts : ouvert par défaut sur ordinateur, replié sur mobile
            repos_panel = page.locator("#sidebar-body")
            toggle = page.locator("#sidebar-toggle")
            if vp_name == "mobile":
                expect(repos_panel).to_be_hidden()
                toggle.click()
            expect(repos_panel).to_be_visible()
            expect(page.locator(".repo-card")).to_have_count(3)
            expect(page.locator(".repo-card", has_text="demo-front")).to_contain_text("1 commit(s) à déployer")
            expect(page.locator(".repo-card", has_text="demo-api")).to_contain_text("à jour")
            expect(page.locator('.repo-card[data-repo-name="demo-api"] .live')).to_contain_text("= dernier commit")
            expect(page.locator('.repo-card[data-repo-name="demo-front"] .live')).to_contain_text("autre version")
            expect(page.locator('.repo-card[data-repo-name="demo-deploy"] .live')).to_be_hidden()
            page.screenshot(path=f"{SHOTS}/projet-{label}.png", full_page=True)
            # Bouton « rapports » d'un dépôt = filtre ; re-clic = tous
            chip = page.locator('[data-filter-repo="demo-api"]')
            chip.click()
            expect(page.locator("#count")).to_have_text("4 rapport(s)")
            expect(chip).to_have_attribute("aria-pressed", "true")
            chip.click()
            expect(page.locator("#count")).to_have_text("7 rapport(s)")
            # Repli puis dépli, état mémorisé au rechargement
            toggle.click()
            expect(repos_panel).to_be_hidden()
            expect(toggle).to_have_attribute("aria-expanded", "false")
            page.reload()
            expect(page.locator("#sidebar-body")).to_be_hidden()
            page.locator("#sidebar-toggle").click()
            expect(page.locator("#sidebar-body")).to_be_visible()
            no_horizontal_scroll(page, f"{label} projet panneau")

            # Détail dépliable
            details = page.locator("details").first
            details.locator("summary").click()
            expect(details).to_have_attribute("open", "")

            # Filtres
            page.select_option("select[name=repo]", "demo-api")
            expect(page.locator("#count")).to_have_text("4 rapport(s)")
            page.select_option("select[name=statut]", "echec")
            expect(page.locator("#count")).to_have_text("1 rapport(s)")
            expect(page.locator("#feed .report:visible")).to_have_count(1)
            assert "repo=demo-api" in page.url and "statut=echec" in page.url
            page.select_option("select[name=statut]", "termine")
            expect(page.locator("#no-match")).to_be_visible()
            page.select_option("select[name=repo]", "")
            page.select_option("select[name=statut]", "")
            expect(page.locator("#count")).to_have_text("7 rapport(s)")
            # « Actualiser » recharge la page courante en gardant les filtres
            page.select_option("select[name=statut]", "echec")
            page.evaluate("window.__avant = 1")
            with page.expect_navigation():
                page.get_by_role("link", name="Actualiser").click()
            assert page.evaluate("typeof window.__avant") == "undefined"  # vraie recharge
            assert page.url.endswith("/demo/#statut=echec")
            expect(page.locator("#count")).to_have_text("1 rapport(s)")
            page.select_option("select[name=statut]", "")
            # Filtres restaurés depuis l'URL
            page.goto(f"{BASE}/demo/#statut=pr-ouverte")
            expect(page.locator("#count")).to_have_text("1 rapport(s)")
            ctx.close()
            print(f"OK {label}")
    browser.close()

if errors:
    print("\n".join(errors))
    sys.exit(1)
print("Toutes les vérifications navigateur sont passées.")
