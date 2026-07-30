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
from threading import Lock
from time import monotonic



class KisAuth:

    _shared_token = None
    _token_lock = Lock()
    _shared_error = None
    _retry_after = 0.0

    def __init__(

        self,

        client

    ):

        self.client = client

        self._token = None



    def get_token(self):

        if self._token is not None and not self._token.is_expired:
            return self._token

        shared = type(self)._shared_token
        if shared is not None and not shared.is_expired:
            self._token = shared
            return shared

        with type(self)._token_lock:
            shared = type(self)._shared_token
            if shared is not None and not shared.is_expired:
                self._token = shared
                return shared
            if (
                type(self)._shared_error is not None
                and monotonic() < type(self)._retry_after
            ):
                raise type(self)._shared_error
            try:
                self._token = self._authenticate()
            except Exception as error:
                type(self)._shared_error = error
                type(self)._retry_after = monotonic() + 60.0
                raise
            type(self)._shared_token = self._token
            type(self)._shared_error = None
            type(self)._retry_after = 0.0
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
