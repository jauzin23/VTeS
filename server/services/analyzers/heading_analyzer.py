from bs4 import BeautifulSoup
from typing import Any
from models.issue import Issue
from models.aspet_result import AspetResult
from .base import BaseAnalyzer, get_xpath

class HeadingAnalyzer(BaseAnalyzer):
    async def analyze(self, page: Any, soup: BeautifulSoup, base_url: str = "") -> AspetResult:
        headings = soup.find_all(['h1','h2','h3','h4','h5','h6'])
        issues = []

        # 2.1
        h1_count = sum(1 for h in headings if h.name == 'h1')
        if h1_count == 0:
            issues.append(Issue(rule="2.1", severity="FAIL", message="Nenhum H1 encontrado"))
        elif h1_count > 1:
            issues.append(Issue(rule="2.1", severity="FAIL", message=f"{h1_count} elementos H1 encontrados"))

        # 2.2
        levels = [int(h.name[1]) for h in headings]
        for i in range(1, len(levels)):
            if levels[i] > levels[i-1] + 1:
                issues.append(Issue(
                    rule="2.2", severity="FAIL",
                    message=f"Salto de H{levels[i-1]} para H{levels[i]}",
                    element=str(headings[i])[:200],
                    xpath=get_xpath(headings[i])
                ))

        # 2.3 - Heurística: divs/spans com font-size > 20px e font-weight >= 600
        fake_headings = await self._detect_visual_headings(page)
        issues.extend(fake_headings)

        return AspetResult(aspeto=2, status="ANALYZED", issues=issues)

    async def _detect_visual_headings(self, page: Any) -> list[Issue]:
        issues = []
        try:
            # We execute JS to find fake headings
            js_code = """
            () => {
                function getXPath(el) {
                    const parts = [];
                    while (el && el.nodeType === 1) {
                        let idx = 1;
                        let sib = el.previousElementSibling;
                        while (sib) {
                            if (sib.tagName === el.tagName) idx++;
                            sib = sib.previousElementSibling;
                        }
                        parts.unshift(`${el.tagName.toLowerCase()}[${idx}]`);
                        el = el.parentElement;
                    }
                    return '/' + parts.join('/');
                }

                const results = [];
                const els = document.querySelectorAll('div, span, p');
                for (const el of els) {
                    if (el.closest('nav, button, form, a, [role="button"], [role="navigation"]')) continue;
                    const text = (el.innerText || el.textContent || '').trim();
                    if (!text || text.length < 4 || /^[\\d\\.\\-\\/]+$/.test(text)) continue;

                    const style = window.getComputedStyle(el);
                    const size = parseFloat(style.fontSize);
                    const weight = parseInt(style.fontWeight) || (style.fontWeight === 'bold' ? 700 : 400);
                    if (size > 20 && weight >= 600) {
                        results.push({ html: el.outerHTML.substring(0, 200), xpath: getXPath(el) });
                    }
                }
                return results;
            }
            """
            elements = await page.evaluate(js_code)
            for item in elements:
                issues.append(Issue(
                    rule="2.3", severity="REVIEW",
                    message="Elemento com estilo visual de cabeçalho, mas sem semântica H1-H6.",
                    element=item.get("html", ""),
                    xpath=item.get("xpath", "")
                ))
        except Exception:
            pass
        return issues
