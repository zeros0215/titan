"""
Token Mapper
"""

from datetime import datetime
from datetime import timedelta

from broker.kis.token import KisToken
from broker.kis.dto.token_response import TokenResponse


class TokenMapper:

    @staticmethod
    def to_domain(
        dto: TokenResponse
    ) -> KisToken:

        return KisToken(

            access_token=dto.access_token,

            token_type=dto.token_type,

            expires_at=(
                datetime.now()
                + timedelta(
                    seconds=dto.expires_in
                )
            )

        )