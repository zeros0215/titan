"""
KIS Header Builder
"""

from config.settings import settings

from broker.kis.token import KisToken


class HeaderBuilder:

    @staticmethod
    def json() -> dict:

        return {

            "Content-Type": "application/json"

        }

    @staticmethod
    def authorization(

        token: KisToken,

        tr_id: str

    ) -> dict:

        return {

            "Content-Type": "application/json",

            "authorization": (

                f"Bearer {token.access_token}"

            ),

            "appkey": settings.kis_app_key,

            "appsecret": settings.kis_app_secret,

            "tr_id": tr_id

        }