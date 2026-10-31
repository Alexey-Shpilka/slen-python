import httpx

from slen._config import ClientConfig
from slen._http._wire import phases_of


# The HTTP clients the SDK builds when it is given none: the redirects are not followed, the proxy variables are read.
def sync_pool(config: ClientConfig) -> httpx.Client:
    return httpx.Client(timeout=phases_of(config.timeout, config.connect_timeout), follow_redirects=False)


def async_pool(config: ClientConfig) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=phases_of(config.timeout, config.connect_timeout), follow_redirects=False)
