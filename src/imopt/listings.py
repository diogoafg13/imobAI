"""Módulo OPCIONAL de anúncios. Desligado por omissão (config: listings.enabled).

Regras incorporadas:
- Só corre se listings.enabled = true E o robots.txt do site permitir o caminho.
- Ritmo limitado (min_delay_seconds) e User-Agent identificado.
- Idealista/Imovirtual proíbem scraping nos termos de uso: para esses, o caminho correto é
  a API oficial do Idealista (acesso por pedido) — ver `IdealistaAPI`. Este módulo NÃO
  contorna bloqueios nem autenticação; se o site recusar, falha e pára.
- Cada recolha grava um snapshot imutável com data (data/raw/listings/AAAAMMDD.parquet).
"""
from __future__ import annotations

import time
import urllib.robotparser as rp
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

UA = "imobiliario-pt/0.1 (uso pessoal; contacto no repositório)"


class NotAllowed(RuntimeError):
    pass


def robots_allows(url: str, agent: str = UA) -> bool:
    p = urlparse(url)
    parser = rp.RobotFileParser()
    parser.set_url(f"{p.scheme}://{p.netloc}/robots.txt")
    try:
        parser.read()
    except Exception as e:  # noqa: BLE001
        raise NotAllowed(f"não foi possível ler robots.txt: {e}") from e
    return parser.can_fetch(agent, url)


class PoliteFetcher:
    def __init__(self, min_delay: float = 5.0, respect_robots: bool = True):
        self.min_delay, self.respect_robots, self._last = min_delay, respect_robots, 0.0
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA

    def get(self, url: str) -> requests.Response:
        if self.respect_robots and not robots_allows(url):
            raise NotAllowed(f"robots.txt não permite: {url}")
        wait = self.min_delay - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        r = self.s.get(url, timeout=30)
        self._last = time.time()
        if r.status_code in (401, 403, 429):
            raise NotAllowed(f"{r.status_code} de {url}: acesso recusado, a parar (sem contornos)")
        r.raise_for_status()
        return r


@dataclass
class IdealistaAPI:
    """Cliente mínimo da API oficial (OAuth2 client_credentials). Requer chave aprovada pela Idealista."""
    api_key: str
    secret: str
    base: str = "https://api.idealista.com"

    def token(self) -> str:
        r = requests.post(f"{self.base}/oauth/token", auth=(self.api_key, self.secret),
                          data={"grant_type": "client_credentials", "scope": "read"}, timeout=30)
        r.raise_for_status()
        return r.json()["access_token"]

    def search(self, params: dict, country: str = "pt") -> dict:
        r = requests.post(f"{self.base}/3.5/{country}/search", params=params,
                          headers={"Authorization": f"Bearer {self.token()}"}, timeout=30)
        r.raise_for_status()
        return r.json()
