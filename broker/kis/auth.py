"""
KIS OAuth
"""


from broker.kis.constants import (
    TOKEN_URL,
    GRANT_TYPE,
)


from broker.kis.dto.token_response import (
    TokenResponse,
)


from broker.kis.mapper.token_mapper import (
    TokenMapper,
)


from broker.kis.header import HeaderBuilder

from broker.kis.exception import (
    KisAuthenticationException,
)


from config.settings import settings



class KisAuth:


    def __init__(

        self,

        client

    ):

        self.client = client

        self._token = None



    def get_token(self):

        if (

            self._token is None

            or

            self._token.is_expired

        ):

            self._token = self._authenticate()


        return self._token



    def _authenticate(self):


        headers = HeaderBuilder.json()


        body = {


            "grant_type": GRANT_TYPE,


            "appkey": settings.kis_app_key,


            "appsecret": settings.kis_app_secret


        }



        response = self.client.post(

            TOKEN_URL,

            headers=headers,

            json=body

        )


        data = response.json()



        #
        # 인증 실패 처리
        #
        if "access_token" not in data:


            raise KisAuthenticationException(

                data.get(

                    "msg_cd",

                    "AUTH_ERROR"

                ),

                data.get(

                    "msg1",

                    "Token Issue Failed"

                )

            )



        dto = TokenResponse.from_json(

            data

        )



        return TokenMapper.to_domain(

            dto

        )