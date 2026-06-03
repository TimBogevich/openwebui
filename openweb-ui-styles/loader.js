/* ==========================================================================
   ГЦУ Ассистент — Open WebUI Brand Override
   - Removes "(Open WebUI)" suffix forced by env.py
   - The placeholder greeting block (avatar + "Здравствуйте"/model name) is
     hidden entirely via custom.css — no JS replacement needed here.
   - Forces the sidebar to always start open by pinning localStorage.sidebar
     to "true" BEFORE SvelteKit reads the store on hydration.
   ========================================================================== */
(function () {
  "use strict";

  // ---- 0. Sidebar always open --------------------------------------------
  // Open WebUI persists sidebar state in `localStorage["sidebar"]` ("true"/"false").
  // This <script> tag is `defer`-loaded from <head>, but it still runs BEFORE
  // SvelteKit hydrates the page, so writing the value here is enough to make
  // the sidebar render in the opened state on every page load.
  try {
    localStorage.setItem("sidebar", "true");
  } catch (_) {}

  // ---- 0b. Splash logo -> favicon ----------------------------------------
  // index.html inline-скрипт создаёт <img id="logo" src="/static/splash.png">
  // и prepend-ит его в #splash-screen на DOMContentLoaded.
  // Перехватываем создание и принудительно ставим src=/static/favicon.png.
  // Делаем это до DOMContentLoaded — наблюдатель ловит появление #logo.
  function rewriteSplashLogo(node) {
    if (
      node &&
      node.nodeType === 1 &&
      node.tagName === "IMG" &&
      node.id === "logo"
    ) {
      node.src = "/static/favicon.png";
    }
  }
  const splashObs = new MutationObserver((muts) => {
    for (const m of muts) {
      for (const n of m.addedNodes) rewriteSplashLogo(n);
    }
    // Если #logo уже вставлен — обновим и выйдем
    const existing = document.getElementById("logo");
    if (existing && existing.tagName === "IMG") {
      rewriteSplashLogo(existing);
    }
  });
  splashObs.observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
  // Подстраховка: после DOMContentLoaded ещё раз и выключаем observer.
  document.addEventListener("DOMContentLoaded", () => {
    const logo = document.getElementById("logo");
    if (logo && logo.tagName === "IMG") logo.src = "/static/favicon.png";
    setTimeout(() => splashObs.disconnect(), 3000);
  });

  const SUFFIX_RE = /\s*\(Open WebUI\)\s*/gi;

  // ---- 1. <title> ---------------------------------------------------------
  function fixTitle() {
    if (document.title && SUFFIX_RE.test(document.title)) {
      document.title = document.title.replace(SUFFIX_RE, "");
    }
  }
  fixTitle();

  const titleEl = document.querySelector("title");
  if (titleEl) {
    new MutationObserver(fixTitle).observe(titleEl, { childList: true });
  }
  new MutationObserver(fixTitle).observe(document.head, {
    childList: true,
    subtree: true,
  });

  // ---- 2. Strip "(Open WebUI)" from any visible text node -----------------
  function stripFromTextNodes(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    let n;
    while ((n = walker.nextNode())) {
      if (n.nodeValue && SUFFIX_RE.test(n.nodeValue)) {
        n.nodeValue = n.nodeValue.replace(SUFFIX_RE, "");
      }
    }
  }

  function runAll() {
    try {
      stripFromTextNodes(document.body || document.documentElement);
    } catch (_) {}
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", runAll);
  } else {
    runAll();
  }

  const bodyObserver = new MutationObserver(() => {
    fixTitle();
    runAll();
  });

  function startBodyObserver() {
    if (document.body) {
      bodyObserver.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    } else {
      setTimeout(startBodyObserver, 50);
    }
  }
  startBodyObserver();

  // Safety net — re-run periodically for 30s after load (SvelteKit hydration).
  let ticks = 0;
  const tickId = setInterval(() => {
    fixTitle();
    runAll();
    if (++ticks >= 60) clearInterval(tickId);
  }, 500);
})();
