"""
HTML processor for iframe preview.

Uses REGEX-ONLY approach (not BeautifulSoup) so the DOM structure is
preserved byte-for-byte from Playwright's render.  This keeps every
XPath that the analyzers generated valid inside the iframe.

Steps:
  1. Inject a real static <base href="..."> tag at the start of <head>
  2. Absolutize relative URLs in <link href>, <script src>, <img src>, <source src>
     using regex so no DOM element is added/removed/reordered.
  3. Inject the interactive postMessage script before </body>.
"""

import re
from urllib.parse import urljoin

# ─── Interactive script ───────────────────────────────────────────────────────

INTERACTIVE_SCRIPT = """<script>
(function () {
  var s = document.createElement('style');
  s.textContent =
    '.tes-hl{outline:3px solid #f59e0b!important;' +
    'background:rgba(245,158,11,.13)!important;' +
    'scroll-margin-top:80px;transition:outline .15s,background .15s}';
  (document.head || document.documentElement).appendChild(s);

  var cur = null;
  function clear() { if (cur) { cur.classList.remove('tes-hl'); cur = null; } }
  function hl(el) {
    clear();
    if (!el) return;
    el.classList.add('tes-hl');
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    cur = el;
  }
  function byXP(xp) {
    try {
      return document.evaluate(
        xp, document, null,
        XPathResult.FIRST_ORDERED_NODE_TYPE, null
      ).singleNodeValue;
    } catch (_) { return null; }
  }

  window.addEventListener('message', function (e) {
    if (!e.data) return;
    if (e.data.type === 'select-heading') {
      var hs = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'));
      hl(hs[e.data.index] || null);
    }
    if (e.data.type === 'highlight-xpath') {
      var el = byXP(e.data.xpath);
      if (!el && e.data.text) {
        // Fallback: find by text content match
        var all = Array.from(document.querySelectorAll('*'));
        el = all.find(function(n) {
          return (n.innerText || n.textContent || '').trim() === e.data.text.trim();
        }) || null;
      }
      hl(el);
    }
  });

  document.addEventListener('click', function (e) {
    var el = e.target.closest('h1,h2,h3,h4,h5,h6');
    if (el) {
      var hs = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'));
      window.parent.postMessage({ type: 'heading-clicked', index: hs.indexOf(el) }, '*');
    }
  }, true);
})();
</script>"""


# ─── URL helpers ──────────────────────────────────────────────────────────────

def _fix_url(url: str, base_url: str) -> str:
    """Make a single URL absolute. Returns the input unchanged if already absolute."""
    url = url.strip()
    if not url:
        return url
    if url.startswith('//'):
        return 'https:' + url
    if url.startswith(('http://', 'https://', 'data:', 'blob:',
                        '#', 'javascript:', 'mailto:', 'tel:')):
        return url
    return urljoin(base_url, url)


def _fix_tag_attr(html: str, tag: str, attr: str, base_url: str) -> str:
    """
    Absolutize URLs in <tag attr="..."> using regex.
    The HTML structure is NOT parsed - only the attribute value is replaced.
    """
    # Match <tag ...whitespace... attr="url"> or attr='url'
    # The tag may have other attributes before `attr`.
    pattern = re.compile(
        rf'(<{tag}\b[^>]*?\b{attr}=)(["\'])([^"\']*)\2',
        re.IGNORECASE | re.DOTALL,
    )

    def replacer(m: re.Match) -> str:
        return m.group(1) + m.group(2) + _fix_url(m.group(3), base_url) + m.group(2)

    return pattern.sub(replacer, html)


# ─── Main entry point ─────────────────────────────────────────────────────────

def inject_iframe_script(html: str, final_url: str) -> str:
    """
    Process Playwright-rendered HTML for use as an iframe srcDoc.

    Critically, this function uses ONLY string/regex operations so that
    the DOM structure (element order, sibling counts) is identical to what
    Playwright saw when it generated the XPaths. If BeautifulSoup were used
    to re-serialize the HTML, sibling indices in XPaths would shift and
    'highlight-xpath' postMessages would silently fail.
    """
    if not html:
        return html

    # ── 1. Inject static <base> tag at the start of <head> ──────────────────
    #
    # Must be the FIRST element inside <head> so the browser uses it to
    # resolve all subsequent <link href> and <script src> before fetching.
    # Adding it via JavaScript is too late - stylesheets are fetched during
    # HTML parsing, before any script runs.

    base_tag = f'<base href="{final_url}" target="_blank">'

    head_match = re.search(r'<head[^>]*>', html, re.IGNORECASE)
    if head_match:
        insert_at = head_match.end()
        # If a <base> already exists, replace its href instead of adding another
        existing_base = re.search(r'<base\b[^>]*/?\s*>', html, re.IGNORECASE)
        if existing_base:
            html = re.sub(
                r'<base\b[^>]*/?\s*>',
                base_tag,
                html,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            html = html[:insert_at] + base_tag + html[insert_at:]
    else:
        # No <head> tag - prepend
        html = base_tag + html

    # ── 2. Absolutize relative asset URLs (regex, no DOM parse) ─────────────

    html = _fix_tag_attr(html, 'link',   'href',   final_url)
    html = _fix_tag_attr(html, 'script', 'src',    final_url)
    html = _fix_tag_attr(html, 'img',    'src',    final_url)
    html = _fix_tag_attr(html, 'source', 'src',    final_url)
    html = _fix_tag_attr(html, 'video',  'src',    final_url)
    html = _fix_tag_attr(html, 'audio',  'src',    final_url)

    # ── 3. Inject interactive postMessage script before </body> ──────────────

    body_close = re.search(r'</body\s*>', html, re.IGNORECASE)
    if body_close:
        html = html[:body_close.start()] + INTERACTIVE_SCRIPT + html[body_close.start():]
    else:
        html += INTERACTIVE_SCRIPT

    return html
