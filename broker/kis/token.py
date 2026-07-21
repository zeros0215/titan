"""
KIS Token Domain
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class KisToken:

    access_token: str

    token_type: str

    expires_at: datetime

    @property
    def is_expired(self) -> bool:

        return datetime.now() >= self.expires_at