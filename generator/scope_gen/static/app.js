// SCOPE — JavaScript minimal, sans framework : heures locales + filtres.
(function () {
  "use strict";

  // Affiche les dates dans le fuseau du navigateur.
  var fmt = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
  document.querySelectorAll("time[datetime]").forEach(function (t) {
    var d = new Date(t.getAttribute("datetime"));
    if (!isNaN(d)) { t.title = t.textContent; t.textContent = fmt.format(d); }
  });

  // Bouton « Actualiser » : recharge la page courante en gardant les filtres
  // (#repo=…&statut=…) ; nginx sert les pages en no-cache.
  var refresh = document.getElementById("refresh");
  if (refresh) {
    refresh.addEventListener("click", function (ev) {
      ev.preventDefault();
      refresh.classList.add("loading");
      refresh.textContent = "Actualisation…";
      location.reload();
    });
  }

  // Âge de la page : « il y a 7 min », en alerte au-delà de 30 min (génération en panne ?).
  var age = document.querySelector(".top .age time");
  if (age) {
    var minutes = Math.round((Date.now() - new Date(age.getAttribute("datetime"))) / 60000);
    if (!isNaN(minutes) && minutes >= 0) {
      var rel = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
      age.textContent = minutes < 60 ? rel.format(-minutes, "minute") : rel.format(-Math.round(minutes / 60), "hour");
      if (minutes > 30) age.parentNode.classList.add("stale");
    }
  }

  // Panneau des dépôts : repliable, état mémorisé par navigateur.
  var layout = document.getElementById("layout");
  var toggle = document.getElementById("sidebar-toggle");
  var KEY = "scope.sidebar.collapsed";
  function setCollapsed(c) {
    layout.classList.toggle("collapsed", c);
    toggle.setAttribute("aria-expanded", String(!c));
    toggle.title = c ? "Déplier le panneau" : "Replier le panneau";
    toggle.querySelector("[aria-hidden]").textContent = c ? "»" : "«";
    toggle.querySelector(".sr-only").textContent = toggle.title;
  }
  if (layout && toggle) {
    var stored = null;
    try { stored = localStorage.getItem(KEY); } catch (e) { /* stockage indisponible */ }
    setCollapsed(stored === null ? window.matchMedia("(max-width: 860px)").matches : stored === "1");
    toggle.addEventListener("click", function () {
      var c = !layout.classList.contains("collapsed");
      setCollapsed(c);
      try { localStorage.setItem(KEY, c ? "1" : "0"); } catch (e) { /* ignoré */ }
    });
  }

  // Santé de l'application : appel direct depuis le navigateur (l'application
  // doit autoriser CORS), toutes les 60 s. Comprend { status, services, versions }.
  var health = document.getElementById("health");
  if (health) {
    var link = health.querySelector("a");
    var OK = ["ok", "up", "healthy", "pass", "passing"];
    var DEGRADED = ["degraded", "warn", "warning", "partial"];
    var setHealth = function (label, cls, title) {
      link.textContent = label;
      link.className = "badge " + cls;
      link.title = title;
    };
    var showVersions = function (versions) {
      document.querySelectorAll(".repo-card[data-repo-name]").forEach(function (card) {
        var v = versions && versions[card.dataset.repoName];
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
        else if (v === card.dataset.deploySha) { b.className = "badge s-bloque"; b.textContent = "= version GitOps"; }
        else { b.className = "badge pr-unknown"; b.textContent = "autre version"; }
        dd.appendChild(code); dd.appendChild(document.createTextNode(" ")); dd.appendChild(b);
        row.hidden = false;
      });
    };
    var check = function () {
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
            var detail = "";
            var suffix = "";
            if (services) {
              var names = Object.keys(services);
              var up = names.filter(function (n) { return OK.indexOf(String(services[n]).toLowerCase()) >= 0; });
              suffix = " · " + up.length + "/" + names.length + " services";
              detail = names.map(function (n) { return n + " : " + services[n]; }).join("\n") + "\n";
            }
            var title = detail + "HTTP " + r.status + " · vérifié à " + at;
            if (r.ok && (OK.indexOf(status) >= 0 || !status)) setHealth("OK" + suffix, "s-termine", title);
            else if (DEGRADED.indexOf(status) >= 0) setHealth("Dégradé" + suffix, "s-bloque", title);
            else setHealth("KO" + (suffix || " · HTTP " + r.status), "s-echec", title);
            showVersions(body && body.versions);
          });
        })
        .catch(function () {
          setHealth("injoignable", "pr-unknown",
            "Pas de réponse en 5 s, ou l'application n'autorise pas CORS · vérifié à " + at);
          showVersions(null);
        })
        .then(function () { clearTimeout(timer); });
    };
    check();
    setInterval(check, 60000);
  }

  var form = document.getElementById("filters");
  if (!form) return;
  var items = Array.prototype.slice.call(document.querySelectorAll("#feed .report"));
  var count = document.getElementById("count");
  var noMatch = document.getElementById("no-match");

  // Les filtres sont gardés dans l'URL (#repo=…&statut=…) pour pouvoir les partager.
  function readHash() {
    var p = new URLSearchParams(location.hash.slice(1));
    ["repo", "statut"].forEach(function (k) {
      var sel = form.elements[k];
      if (p.has(k) && Array.prototype.some.call(sel.options, function (o) { return o.value === p.get(k); })) {
        sel.value = p.get(k);
      }
    });
  }

  function apply() {
    var repo = form.elements.repo.value;
    var statut = form.elements.statut.value;
    var shown = 0;
    items.forEach(function (el) {
      var ok = (!repo || el.dataset.repo === repo) && (!statut || el.dataset.statut === statut);
      el.hidden = !ok;
      if (ok) shown++;
    });
    count.textContent = shown + " rapport(s)";
    chips.forEach(function (c) { c.setAttribute("aria-pressed", String(c.dataset.filterRepo === repo)); });
    noMatch.hidden = shown > 0 || items.length === 0;
    var p = new URLSearchParams();
    if (repo) p.set("repo", repo);
    if (statut) p.set("statut", statut);
    var h = p.toString();
    history.replaceState(null, "", h ? "#" + h : location.pathname + location.search);
  }

  // Bouton « rapports » d'un dépôt : filtre le fil sur ce dépôt (re-clic : tous).
  var chips = Array.prototype.slice.call(document.querySelectorAll("[data-filter-repo]"));
  chips.forEach(function (c) {
    c.addEventListener("click", function () {
      var sel = form.elements.repo;
      sel.value = sel.value === c.dataset.filterRepo ? "" : c.dataset.filterRepo;
      apply();
      if (window.matchMedia("(max-width: 860px)").matches) form.scrollIntoView({ behavior: "smooth" });
    });
  });

  form.addEventListener("change", apply);
  form.addEventListener("submit", function (ev) { ev.preventDefault(); });
  window.addEventListener("hashchange", function () { form.reset(); readHash(); apply(); });
  readHash();
  apply();
})();
