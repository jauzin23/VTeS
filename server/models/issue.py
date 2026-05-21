from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

@dataclass
class Issue:
    rule: str
    severity: str
    message: str
    element: Optional[str] = None
    xpath: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    evidence_video: bool = False
