import re
from urllib.parse import urljoin

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
      var el = null;
      if (e.data.xpath) {
        el = byXP(e.data.xpath);
      }
      if (!el && typeof e.data.index === 'number') {
        var hs = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'));
        el = hs[e.data.index] || null;
      }
      if (!el && e.data.text) {
        var all = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'));
        var targetText = e.data.text.replace(/\\s+/g, ' ').trim();
        el = all.find(function(n) {
          return (n.innerText || n.textContent || '').replace(/\\s+/g, ' ').trim() === targetText;
        }) || null;
      }
      hl(el);
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

def _fix_url(url: str, base_url: str) -> str:
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
    pattern = re.compile(
        rf'(<{tag}\b[^>]*?\b{attr}=)(["\'])([^"\']*)\2',
        re.IGNORECASE | re.DOTALL,
    )

    def replacer(m: re.Match) -> str:
        return m.group(1) + m.group(2) + _fix_url(m.group(3), base_url) + m.group(2)

    return pattern.sub(replacer, html)

def inject_iframe_script(html: str, final_url: str) -> str:
    if not html:
        return html

    base_tag = f'<base href="{final_url}" target="_blank">'

    head_match = re.search(r'<head[^>]*>', html, re.IGNORECASE)
    if head_match:
        insert_at = head_match.end()
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
        html = base_tag + html

    html = _fix_tag_attr(html, 'link',   'href',   final_url)
    html = _fix_tag_attr(html, 'img',    'src',    final_url)
    html = _fix_tag_attr(html, 'source', 'src',    final_url)
    html = _fix_tag_attr(html, 'video',  'src',    final_url)
    html = _fix_tag_attr(html, 'audio',  'src',    final_url)

    html = re.sub(r'(<script\b[^>]*?)\s+type=["\'][^"\']*["\']', r'\1', html, flags=re.IGNORECASE)
    html = re.sub(r'<script\b', '<script type="javascript/blocked"', html, flags=re.IGNORECASE)

    body_close = re.search(r'</body\s*>', html, re.IGNORECASE)
    if body_close:
        html = html[:body_close.start()] + INTERACTIVE_SCRIPT + html[body_close.start():]
    else:
        html += INTERACTIVE_SCRIPT

    return html
