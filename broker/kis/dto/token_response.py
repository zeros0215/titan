"""
KIS OAuth Token Response DTO
"""

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class TokenResponse:

    access_token: str

    token_type: str

    expires_in: int

    @classmethod
    def from_json(cls, data: dict) -> "TokenResponse":

        return cls(

            access_token=data["access_token"],

            token_type=data["token_type"],

            expires_in=int(data["expires_in"])

        )