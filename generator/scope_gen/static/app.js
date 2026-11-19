// SCOPE — JavaScript minimal, sans framework : heures locales, filtres et
// mise à jour en direct (la page relit etat.json et se remplace quand le
// contenu change, en gardant filtres et sections dépliées).
(function () {
  "use strict";

  var fmt = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
  var rel = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

  function meta(name) {
    var m = document.querySelector('meta[name="' + name + '"]');
    return m ? m.getAttribute("content") : "";
  }

  // Dates dans le fuseau du navigateur.
  function localTimes(root) {
    root.querySelectorAll("time[datetime]").forEach(function (t) {
      var d = new Date(t.getAttribute("datetime"));
      if (!isNaN(d) && !t.title) { t.title = t.textContent; t.textContent = fmt.format(d); }
    });
  }

  // --- Filtres (page projet), gardés dans l'URL : #depot=…&statut=… ----------
  var form;
  function cards() { return Array.prototype.slice.call(document.querySelectorAll("#main .demande")); }

  function readHash() {
    if (!form) return;
    var p = new URLSearchParams(location.hash.slice(1));
    ["depot", "statut"].forEach(function (k) {
      var sel = form.elements[k];
      var v = p.get(k) || "";
      sel.value = Array.prototype.some.call(sel.options, function (o) { return o.value === v; }) ? v : "";
    });
  }

  function apply(writeHash) {
    if (!form) return;
    var depot = form.elements.depot.value;
    var statut = form.elements.statut.value;
    var all = cards();
    var shown = 0;
    all.forEach(function (el) {
      var ok = (!depot || el.dataset.depot === depot) && (!statut || el.dataset.statut === statut);
      el.hidden = !ok;
      if (ok) shown++;
    });
    document.querySelectorAll("#main .bloc").forEach(function (s) {
      var c = s.querySelectorAll(".demande");
      if (!c.length) return;
      s.hidden = Array.prototype.every.call(c, function (el) { return el.hidden; });
    });
    document.getElementById("count").textContent = shown + " demande(s)";
    document.getElementById("no-match").hidden = shown > 0 || all.length === 0;
    document.querySelectorAll("[data-filtre-depot]").forEach(function (c) {
      c.setAttribute("aria-pressed", String(c.dataset.filtreDepot === depot));
    });
    if (writeHash) {
      var p = new URLSearchParams();
      if (depot) p.set("depot", depot);
      if (statut) p.set("statut", statut);
      var h = p.toString();
      history.replaceState(null, "", h ? "#" + h : location.pathname + location.search);
    }
  }

  // --- Panneau des dépôts (avec token) : repliable, état mémorisé ---------
  var KEY = "scope.sidebar.collapsed";
  function initSidebar() {
    var layout = document.getElementById("layout");
    var toggle = document.getElementById("sidebar-toggle");
    if (!layout || !toggle) return;
    function setCollapsed(c) {
      layout.classList.toggle("collapsed", c);
      toggle.setAttribute("aria-expanded", String(!c));
      toggle.title = c ? "Déplier le panneau" : "Replier le panneau";
      toggle.querySelector("[aria-hidden]").textContent = c ? "»" : "«";
      toggle.querySelector(".sr-only").textContent = toggle.title;
    }
    var stored = null;
    try { stored = localStorage.getItem(KEY); } catch (e) { /* stockage indisponible */ }
    setCollapsed(stored === null ? window.matchMedia("(max-width: 860px)").matches : stored === "1");
    toggle.addEventListener("click", function () {
      var c = !layout.classList.contains("collapsed");
      setCollapsed(c);
      try { localStorage.setItem(KEY, c ? "1" : "0"); } catch (e) { /* ignoré */ }
    });
  }

  // --- Santé de l'application (projects/<projet>.yml : sante) ---------------
  // Appel direct depuis le navigateur (CORS requis), toutes les 60 s.
  // Comprend { status, services, versions }. Le dernier résultat est réappliqué
  // après chaque mise à jour en direct de la page.
  var OK = ["ok", "up", "healthy", "pass", "passing"];
  var DEGRADED = ["degraded", "warn", "warning", "partial"];
  var lastHealth = null;
  function showHealth() {
    var health = document.getElementById("health");
    if (!health || !lastHealth) return;
    var link = health.querySelector("a");
    link.textContent = lastHealth.label;
    link.className = "badge " + lastHealth.cls;
    link.title = lastHealth.title;
    document.querySelectorAll(".repo-card[data-repo-name]").forEach(function (card) {
      var v = lastHealth.versions && lastHealth.versions[card.dataset.repoName];
      var row = card.querySelector(".live");
      if (!row) return;
      if (typeof v !== "string" || !v) { row.hidden = true; return; }
      var dd = row.querySelector("dd");
      dd.textContent = "";
      var code = document.createElement("code");
      code.textContent = /^[0-9a-f]{40}$/.test(v) ? v.slice(0, 7) : v;
      code.title = v;
      var b = document.createElement("span");
      if (v === card.dataset.lastSha) { b.className = "badge s-termine"; b.textContent = "= dernier commit"; }
      else if (v === card.dataset.deploySha) { b.className = "badge s-attente"; b.textContent = "= version GitOps"; }
      else { b.className = "badge"; b.textContent = "autre version"; }
      dd.appendChild(code); dd.appendChild(document.createTextNode(" ")); dd.appendChild(b);
      row.hidden = false;
    });
  }
  function checkHealth() {
    var health = document.getElementById("health");
    if (!health) return;
    var ctrl = new AbortController();
    var timer = setTimeout(function () { ctrl.abort(); }, 5000);
    var at = new Date().toLocaleTimeString();
    fetch(health.dataset.url, { cache: "no-store", signal: ctrl.signal })
      .then(function (r) {
        return r.text().then(function (text) {
          var body = null;
          try { body = JSON.parse(text); } catch (e) { /* corps non JSON */ }
          var status = String((body && body.status) || "").toLowerCase();
          var services = body && body.services && typeof body.services === "object" ? body.services : null;
          var detail = "", suffix = "";
          if (services) {
            var names = Object.keys(services);
            var up = names.filter(function (n) { return OK.indexOf(String(services[n]).toLowerCase()) >= 0; });
            suffix = " · " + up.length + "/" + names.length + " services";
            detail = names.map(function (n) { return n + " : " + services[n]; }).join("\n") + "\n";
          }
          var title = detail + "HTTP " + r.status + " · vérifié à " + at;
          var res = { title: title, versions: body && body.versions };
          if (r.ok && (OK.indexOf(status) >= 0 || !status)) { res.label = "OK" + suffix; res.cls = "s-termine"; }
          else if (DEGRADED.indexOf(status) >= 0) { res.label = "Dégradé" + suffix; res.cls = "s-attente"; }
          else { res.label = "KO" + (suffix || " · HTTP " + r.status); res.cls = "s-echec"; }
          lastHealth = res;
        });
      })
      .catch(function () {
        lastHealth = { label: "injoignable", cls: "", versions: null,
          title: "Pas de réponse en 5 s, ou l'application n'autorise pas CORS · vérifié à " + at };
      })
      .then(function () { clearTimeout(timer); showHealth(); });
  }

  function initPage() {
    localTimes(document);
    initSidebar();
    showHealth();
    form = document.getElementById("filters");
    if (!form) return;
    form.addEventListener("change", function () { apply(true); });
    form.addEventListener("submit", function (ev) { ev.preventDefault(); });
    document.querySelectorAll("[data-filtre-depot]").forEach(function (c) {
      c.addEventListener("click", function () {
        var sel = form.elements.depot;
        sel.value = sel.value === c.dataset.filtreDepot ? "" : c.dataset.filtreDepot;
        apply(true);
      });
    });
    readHash();
    apply(false);
  }

  window.addEventListener("hashchange", function () { readHash(); apply(false); });
  initPage();
  if (document.getElementById("health")) { checkHealth(); setInterval(checkHealth, 60000); }

  // --- Mise à jour en direct ------------------------------------------------
  var intervalle = parseFloat(meta("scope-intervalle")) || 0;
  if (!intervalle) return; // site généré une fois : rien à surveiller
  var empreinte = meta("scope-empreinte");
  var code = meta("scope-code");
  var root = document.body.dataset.root || ".";
  var age = document.getElementById("age");
  var busy = false;

  function showAge(verifie) {
    var d = new Date(verifie);
    if (isNaN(d)) return;
    var s = Math.max(0, Math.round((Date.now() - d) / 1000));
    var limite = Math.max(60, intervalle * 10);
    age.textContent = s < 60 ? "En direct · vérifié " + rel.format(-s, "second")
                             : "Vérifié " + rel.format(-Math.round(s / 60), "minute");
    age.classList.toggle("stale", s > limite);
    age.title = s > limite ? "La génération semble arrêtée (./scope.sh logs)" : "Relu toutes les " + intervalle + " s";
  }

  function swap(html) {
    var doc = new DOMParser().parseFromString(html, "text/html");
    var main = doc.getElementById("main");
    if (!main) return;
    var open = Array.prototype.map.call(document.querySelectorAll("#main details[open][id]"), function (d) { return d.id; });
    var y = window.scrollY;
    document.getElementById("main").replaceWith(document.adoptNode(main));
    var footer = doc.querySelector("footer");
    if (footer) document.querySelector("footer").replaceWith(document.adoptNode(footer));
    open.forEach(function (id) { var d = document.getElementById(id); if (d) d.open = true; });
    empreinte = doc.querySelector('meta[name="scope-empreinte"]').getAttribute("content");
    document.querySelector('meta[name="scope-empreinte"]').setAttribute("content", empreinte);
    document.title = doc.title;
    initPage();
    window.scrollTo(0, y);
    document.dispatchEvent(new CustomEvent("scope:maj"));
  }

  function poll() {
    if (busy) return;
    busy = true;
    fetch(root + "/etat.json", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (etat) {
        if (!etat) return null;
        showAge(etat.verifie_a);
        // SCOPE a été mis à jour : on recharge tout (en-tête, CSS, JS), filtres compris (hash).
        if (etat.code && code && etat.code !== code) { location.reload(); return null; }
        if (etat.empreinte === empreinte) return null;
        return fetch(location.pathname + location.search, { cache: "no-store" })
          .then(function (r) { return r.ok ? r.text() : null; })
          .then(function (html) { if (html) swap(html); });
      })
      .catch(function () { age.textContent = "Hors ligne"; age.classList.add("stale"); })
      .then(function () { busy = false; });
  }

  poll();
  setInterval(poll, Math.max(1, intervalle) * 1000);
})();
