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

        return AspetResult(aspeto=2, status="ANALYZED", issues=issues)
