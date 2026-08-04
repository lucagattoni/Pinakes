// Number the page title and its sections on the docs site, deriving the page's
// number (e.g. "2.1") from its entry in the left navigation. So the H1 becomes
// "2.1 CLI reference" and its sections become "2.1.1 …", "2.1.2 …".
//
// Done in JS (not in the Markdown) so the source files, their heading anchors,
// and the GitHub rendering stay clean. That is not cosmetic here: docs/STATUS.md's
// line 3 is parsed by tools/status_header_gate.py, and heading anchors are linked
// from source comments across src/ — numbering them in the Markdown would break
// both. Uses Material's `document$` so it re-runs on instant navigation.
// Idempotent via a data-flag guard.
document$.subscribe(function () {
  var content = document.querySelector(".md-content");
  if (!content) return;

  // The current page's nav link text starts with its number, e.g. "2.1 CLI". The trailing dot is
  // optional because a chapter that is a single page is labelled "1. Guide", not "1.1 Guide" —
  // requiring bare digits would silently leave that whole page unnumbered.
  var activeLink = document.querySelector(".md-nav__link--active");
  var match = activeLink && activeLink.textContent.trim().match(/^(\d+(?:\.\d+)*)\.?\s/);
  var pageNum = match ? match[1] : null;
  if (!pageNum) return; // Home and other unnumbered pages: leave untouched.

  function prefix(el, num) {
    if (!el || el.dataset.numbered) return;
    el.dataset.numbered = "1";
    el.insertBefore(document.createTextNode(num + " "), el.firstChild);
    // Keep the right-hand table of contents in sync. With instant navigation the
    // TOC hrefs are absolute (".../page/#slug"), so match on the "#slug" suffix.
    if (el.id) {
      var idEsc = window.CSS && CSS.escape ? CSS.escape(el.id) : el.id;
      document
        .querySelectorAll('a.md-nav__link[href$="#' + idEsc + '"]')
        .forEach(function (toc) {
          if (toc.dataset.numbered) return;
          toc.dataset.numbered = "1";
          toc.insertBefore(document.createTextNode(num + " "), toc.firstChild);
        });
    }
  }

  // Page title (the "chapter"/"section" title): "2.1".
  prefix(content.querySelector("h1"), pageNum);

  // Sections and subsections: "2.1.1", "2.1.1.1".
  var h2 = 0, h3 = 0;
  content.querySelectorAll("h2, h3").forEach(function (h) {
    if (h.dataset.numbered) return;
    var num;
    if (h.tagName === "H2") {
      h2 += 1; h3 = 0;
      num = pageNum + "." + h2;
    } else {
      h3 += 1;
      num = pageNum + "." + h2 + "." + h3;
    }
    prefix(h, num);
  });
});
