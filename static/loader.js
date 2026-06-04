// ============================================================
//  РЖД Интер — Open WebUI branding loader
//  • scrubs "Open WebUI" -> "РЖД Интер" in title + DOM
//  • forces sidebar open
//  • builds the sidebar header  [ logo glyph | ИНТЕР ]
//  • drops a live-DB status dot into the footer profile
//  All DOM work is idempotent and re-armed via MutationObserver,
//  because the Svelte SPA re-renders the sidebar.
// ============================================================
(function () {
  var FULL      = "РЖД Интер";
  var WORD      = "ИНТЕР";
  var LOGO_DARK = "/static/rzd_logo_dark.png"; // light-grey logo for dark sidebar

  // Force the sidebar open before hydration.
  try { localStorage.setItem("sidebar", "true"); } catch (e) {}

  /* ---------- title / text scrubbing ---------- */
  function scrub(t) {
    if (!t) return t;
    return t
      .replace(/ГЦУ Ассистент \(Open WebUI\)/gi, FULL)
      .replace(/РЖД Интер \(Open WebUI\)/gi, FULL)
      .replace(/РЖД \(Open WebUI\)/gi, FULL)
      .replace(/\(Open\s*WebUI\)/gi, "")
      .replace(/Open\s*WebUI/gi, FULL);
  }
  function fixTitle() {
    if (/open\s*webui/i.test(document.title) || document.title !== FULL) {
      document.title = FULL;
    }
  }
  function scrubDom(root) {
    try {
      var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
      var hits = [], n;
      while ((n = w.nextNode())) {
        if (n.nodeValue && /open\s*webui/i.test(n.nodeValue)) hits.push(n);
      }
      hits.forEach(function (node) { node.nodeValue = scrub(node.nodeValue); });
    } catch (e) {}
  }

  /* ---------- branded sidebar header ---------- *
   * Replaces the small "РЖД Интер" text node in the sidebar
   * header with: [logo glyph] | ИНТЕР                         */
  function brandHeader() {
    var sb = document.getElementById("sidebar");
    if (!sb || sb.querySelector("#rzd-brand")) return;

    // Find the leaf element near the top whose text is the app name.
    var candidates = sb.querySelectorAll("a, div, span, h1, button");
    var target = null;
    for (var i = 0; i < candidates.length; i++) {
      var el = candidates[i];
      var t = (el.textContent || "").trim();
      if (t === FULL && el.children.length <= 1) {
        // prefer something in the top ~120px of the sidebar
        var top = el.getBoundingClientRect().top - sb.getBoundingClientRect().top;
        if (top < 120) { target = el; break; }
      }
    }
    if (!target) return;

    var brand = document.createElement("div");
    brand.id = "rzd-brand";
    var img = document.createElement("img");
    img.src = LOGO_DARK; img.alt = "РЖД";
    var word = document.createElement("span");
    word.className = "rzd-word"; word.textContent = WORD;
    brand.appendChild(img); brand.appendChild(word);

    target.setAttribute("data-rzd-hide", "");
    target.parentNode.insertBefore(brand, target);
  }

  /* ---------- live-DB status dot in the footer ---------- *
   * Appends a green dot next to the user/profile button so the
   * footer reads as a clean profile row, not a mystery dot.    */
  function liveDot() {
    var sb = document.getElementById("sidebar");
    if (!sb) return;
    var menu =
      sb.querySelector('[aria-label="User Menu"]') ||
      sb.querySelector('button[id*="user"]');
    if (!menu || menu.querySelector("#rzd-live")) return;
    var dot = document.createElement("span");
    dot.id = "rzd-live";
    dot.title = "В сети · база подключена";
    menu.appendChild(dot);
  }

  /* ---------- tick ---------- */
  function tick() {
    fixTitle();
    if (document.body) {
      scrubDom(document.body);
      try { brandHeader(); } catch (e) {}
      try { liveDot(); } catch (e) {}
    }
  }

  document.addEventListener("DOMContentLoaded", tick);
  window.addEventListener("load", tick);
  var mo = new MutationObserver(tick);
  (function arm() {
    if (document.body) {
      mo.observe(document.body, { childList: true, subtree: true, characterData: true });
      tick();
    } else setTimeout(arm, 50);
  })();
  setInterval(tick, 800);
})();
