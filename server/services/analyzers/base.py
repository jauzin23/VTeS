from abc import ABC, abstractmethod
from typing import Any
from bs4 import BeautifulSoup, Tag
from models.aspet_result import AspetResult

def get_xpath(element: Tag) -> str:
    if not element or not getattr(element, 'name', None):
        return ""
    components = []
    child = element
    for parent in child.parents:
        if parent is None or parent.name == '[document]':
            break
        siblings = parent.find_all(child.name, recursive=False)
        if len(siblings) == 1:
            components.append(child.name)
        else:
            index = siblings.index(child) + 1
            components.append(f'{child.name}[{index}]')
        child = parent
    components.reverse()
    return '/' + '/'.join(components)

class BaseAnalyzer(ABC):
    @abstractmethod
    async def analyze(self, page: Any, soup: BeautifulSoup, base_url: str = "") -> AspetResult:
        pass
