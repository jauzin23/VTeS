from dataclasses import dataclass, field
from typing import List, Optional
from .issue import Issue

@dataclass
class AspetResult:
    aspeto: int
    status: Optional[str] = None
    message: Optional[str] = None
    issues: List[Issue] = field(default_factory=list)
