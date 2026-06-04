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
  var FULL       = "РЖД Интер";
  var WORD       = "ИНТЕР";
  var LOGO_DARK  = "/static/rzd_logo_dark.png"; // light-grey logo for dark sidebar
  var USER_LABEL = "Оператор";                  // footer name (replaces the duplicate brand)

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

    // Hide OWI's ORIGINAL header logo <img> (its favicon glyph, to the left of
    // the app name) so we don't end up with TWO РЖД logos. Our #rzd-brand has
    // its own logo, so any other header-zone <img> is the duplicate.
    var sbTop2 = sb.getBoundingClientRect().top;
    sb.querySelectorAll("img").forEach(function (im) {
      if (im.closest("#rzd-brand")) return;            // keep our glyph
      if ((im.getBoundingClientRect().top - sbTop2) < 110) im.style.display = "none";
    });
  }

  /* ---------- footer profile row ---------- *
   * OWI's footer is the user-menu button: it renders the DB
   * user.name + profile_image_url. We don't rely on a fragile
   * aria-label — we locate the avatar <img> (the last image in
   * the sidebar that isn't our own header glyph), then:
   *   • tag its button with [data-rzd-footer] so CSS can style it
   *   • drop a green "online" badge on the avatar (not loose)
   *   • relabel the name IF it still duplicates the brand        */
  function footerProfile() {
    var sb = document.getElementById("sidebar");
    if (!sb) return;

    // avatar = last <img> in the sidebar that is NOT the header glyph
    var imgs = [].slice.call(sb.querySelectorAll("img")).filter(function (im) {
      return !im.closest("#rzd-brand");
    });
    if (!imgs.length) return;
    var avatar = imgs[imgs.length - 1];

    // the clickable footer container (button / anchor / row)
    var btn = avatar.closest("button, a") || avatar.parentElement;
    if (btn) btn.setAttribute("data-rzd-footer", "");

    // green online badge, anchored to the avatar's wrapper
    var wrap = avatar.parentElement;
    if (wrap && !wrap.querySelector("#rzd-live")) {
      wrap.style.position = wrap.style.position || "relative";
      var dot = document.createElement("span");
      dot.id = "rzd-live";
      dot.title = "В сети · база подключена";
      wrap.appendChild(dot);
    }

    // relabel the footer name only when it still echoes the brand
    if (btn) {
      var w = document.createTreeWalker(btn, NodeFilter.SHOW_TEXT, null);
      var n;
      while ((n = w.nextNode())) {
        if (n.nodeValue && n.nodeValue.trim() === FULL) {
          n.nodeValue = n.nodeValue.replace(FULL, USER_LABEL);
        }
      }
    }
  }

  /* ---------- "Загрузить доклад" in the user menu ---------- *
   * The user-menu dropdown (Настройки / Архив чатов / … / Выход) only exists in
   * the DOM while open. When it appears, we CLONE its "Настройки"/"Settings" row
   * (so styling matches exactly), then swap the label + make it open the
   * standalone uploader (:8810) in a new tab. Idempotent.                      */
  function uploadMenuItem() {
    // find an open menu by locating its "Настройки"/"Settings" row. Menu items
    // often wrap the label in a nested span with an icon, so match by the
    // trimmed text being EXACTLY the label OR containing it as the only words.
    var items = document.querySelectorAll('[role="menuitem"], [data-melt-dropdown-menu-item], .dropdown-menu button, .dropdown-menu a');
    if (!items.length) items = document.querySelectorAll('button, a');
    var settingsRow = null;
    for (var i = 0; i < items.length; i++) {
      var t = (items[i].textContent || "").replace(/\s+/g, " ").trim();
      if (t === "Настройки" || t === "Settings") {
        var menu = items[i].closest('[role="menu"], [data-melt-dropdown-menu], .dropdown-menu, [id*="menu"]');
        if (menu || items[i].getAttribute("role") === "menuitem" ||
            items[i].hasAttribute("data-melt-dropdown-menu-item")) {
          settingsRow = items[i]; break;
        }
      }
    }
    if (!settingsRow) return;
    var container = settingsRow.parentNode;
    if (!container || container.querySelector("#rzd-upload-item")) return;

    var clone = settingsRow.cloneNode(true);
    clone.id = "rzd-upload-item";
    clone.removeAttribute("data-melt-dropdown-menu-item");
    clone.removeAttribute("data-highlighted");
    // relabel: first non-empty text node -> "Загрузить доклад", blank the rest
    var w = document.createTreeWalker(clone, NodeFilter.SHOW_TEXT, null), n, done = false;
    while ((n = w.nextNode())) {
      if (n.nodeValue && n.nodeValue.trim()) {
        n.nodeValue = done ? "" : "Загрузить доклад";
        done = true;
      }
    }
    // swap the gear icon for a FILE icon (replace the cloned <svg>'s inner paths)
    var svg = clone.querySelector("svg");
    if (svg) {
      svg.setAttribute("viewBox", "0 0 24 24");
      svg.setAttribute("fill", "none");
      svg.setAttribute("stroke", "currentColor");
      svg.setAttribute("stroke-width", "2");
      svg.setAttribute("stroke-linecap", "round");
      svg.setAttribute("stroke-linejoin", "round");
      // document/file glyph
      svg.innerHTML =
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>' +
        '<polyline points="14 2 14 8 20 8"></polyline>' +
        '<line x1="12" y1="18" x2="12" y2="12"></line>' +
        '<polyline points="9 15 12 12 15 15"></polyline>';
    }
    // open the uploader on the same host:8810 in a new tab
    var host = location.hostname || "localhost";
    var url = location.protocol + "//" + host + ":8810/";
    clone.addEventListener("click", function (e) {
      e.preventDefault(); e.stopPropagation();
      window.open(url, "_blank", "noopener");
    }, true);
    if (clone.tagName === "A") { clone.href = url; clone.target = "_blank"; }
    // place it right after Настройки
    container.insertBefore(clone, settingsRow.nextSibling);
  }

  /* ---------- tick ---------- */
  function tick() {
    fixTitle();
    if (document.body) {
      scrubDom(document.body);
      try { brandHeader(); } catch (e) {}
      try { uploadMenuItem(); } catch (e) {}
      try { footerProfile(); } catch (e) {}
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
