"""
KIS Session
"""

from broker.kis.auth import KisAuth
from broker.kis.client import KisClient
from broker.kis.header import HeaderBuilder

class KisSession:

    def __init__(self, client: KisClient | None = None):

        self.client = client or KisClient()
        self.auth = KisAuth(self.client)


    def authorization_header(self, tr_id: str):

        token = self.auth.get_token()

        return HeaderBuilder.authorization(
            token=token,
            tr_id=tr_id
        )

    def get(
        self,
        url,
        tr_id,
        params=None
    ):

        headers = self.authorization_header(tr_id)

        return self.client.get(
            url=url,
            headers=headers,
            params=params
        )


    def post(
        self,
        url: str,
        json: dict | None = None,
        headers: dict | None = None,
    ):

        auth_headers = self.authorization_header()

        if headers:
            auth_headers.update(headers)

        return self.client.post(
            url=url,
            headers=auth_headers,
            json=json
        )

    def close(self):

        self.client.close()
