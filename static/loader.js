// РЖД branding loader for Open WebUI.
// Replaces every "Open WebUI" occurrence with "РЖД" in title + DOM, live.
(function () {
  var FULL = "РЖД — Ассистент ГЦУ";
  function scrub(t) {
    if (!t) return t;
    return t
      .replace(/ГЦУ Ассистент \(Open WebUI\)/gi, FULL)
      .replace(/РЖД \(Open WebUI\)/gi, "РЖД")
      .replace(/Open\s*WebUI/gi, "РЖД");
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
  function tick() { fixTitle(); if (document.body) scrubDom(document.body); }
  document.addEventListener("DOMContentLoaded", tick);
  window.addEventListener("load", tick);
  var mo = new MutationObserver(tick);
  (function arm() {
    if (document.body) { mo.observe(document.body, { childList: true, subtree: true, characterData: true }); tick(); }
    else setTimeout(arm, 50);
  })();
  setInterval(fixTitle, 1000);
})();
