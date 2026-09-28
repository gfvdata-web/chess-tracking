"""Etapa 2 — coleta na API pública do Chess.com (PubAPI).

Regras da API respeitadas aqui:
- toda requisição leva um User-Agent identificando o projeto;
- requisições estritamente sequenciais (uma sessão, sem threads);
- 429 (rate limit) e erros transitórios são repetidos com espera crescente.

Coleta incremental: um mês já tratado e marcado como `completo` em
dados/partidas/<usuario>/AAAA-MM.json não é baixado de novo — os arquivos
mensais do Chess.com são imutáveis depois que o mês termina. O mês corrente
(e qualquer mês ainda não completo) é sempre rebaixado.
"""
import json
import logging
import time
from datetime import datetime, timezone

import requests

from src import config

log = logging.getLogger("coleta")

PAUSA_ENTRE_REQUISICOES = 0.5   # segundos; cortesia com a API
MAX_TENTATIVAS = 6


class ErroAPI(RuntimeError):
    pass


class ClienteChessCom:
    def __init__(self, user_agent: str):
        self.sessao = requests.Session()
        self.sessao.headers.update({"User-Agent": user_agent, "Accept": "application/json"})
        self._ultima = 0.0

    def get_json(self, url: str):
        """GET com retry. Retorna o JSON, ou None em 404/410."""
        for tentativa in range(1, MAX_TENTATIVAS + 1):
            espera = PAUSA_ENTRE_REQUISICOES - (time.monotonic() - self._ultima)
            if espera > 0:
                time.sleep(espera)
            try:
                resp = self.sessao.get(url, timeout=30)
            except requests.RequestException as e:
                resp, erro = None, str(e)
            finally:
                self._ultima = time.monotonic()

            if resp is not None:
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in (404, 410):
                    log.warning("%s -> %s (ignorado)", url, resp.status_code)
                    return None
                erro = f"HTTP {resp.status_code}"
                if resp.status_code not in (429, 500, 502, 503, 504):
                    raise ErroAPI(f"{url}: {erro}")

            atraso = 5 * 2 ** (tentativa - 1)
            if resp is not None and resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    atraso = max(atraso, int(retry_after))
            if tentativa == MAX_TENTATIVAS:
                break
            log.warning("%s -> %s; nova tentativa em %ss (%d/%d)",
                        url, erro, atraso, tentativa, MAX_TENTATIVAS)
            time.sleep(atraso)
        raise ErroAPI(f"{url}: falhou após {MAX_TENTATIVAS} tentativas ({erro})")


def _mes_de_url(url: str) -> str:
    ano, mes = url.rstrip("/").split("/")[-2:]
    return f"{ano}-{mes}"


def mes_completo_no_disco(usuario: str, mes: str) -> bool:
    arq = config.dir_partidas(usuario) / f"{mes}.json"
    if not arq.exists():
        return False
    try:
        return bool(json.loads(arq.read_text(encoding="utf-8")).get("completo"))
    except (json.JSONDecodeError, OSError):
        return False


def coletar_perfil(cliente: ClienteChessCom, usuario: str) -> dict:
    perfil = cliente.get_json(f"{config.API_BASE}/player/{usuario}")
    if perfil is None:
        raise ErroAPI(f"Usuário '{usuario}' não encontrado no Chess.com")
    stats = cliente.get_json(f"{config.API_BASE}/player/{usuario}/stats") or {}
    return {"perfil": perfil, "stats": stats}


def coletar_partidas(cliente: ClienteChessCom, usuario: str, completo: bool = False) -> list[dict]:
    """Baixa os meses necessários. Retorna [{mes, completo, games}] do que foi baixado."""
    arquivos = cliente.get_json(f"{config.API_BASE}/player/{usuario}/games/archives") or {}
    urls = arquivos.get("archives", [])
    log.info("%d meses com partidas no Chess.com", len(urls))

    agora = datetime.now(timezone.utc)
    destino = config.dir_brutos(usuario)
    destino.mkdir(parents=True, exist_ok=True)
    baixados = []

    for url in urls:
        mes = _mes_de_url(url)
        if not completo and mes_completo_no_disco(usuario, mes):
            continue
        dados = cliente.get_json(url)
        if dados is None:
            continue
        games = dados.get("games", [])
        # O arquivo de um mês é definitivo depois que o mês acaba; uma folga de
        # 1 dia cobre partidas que terminam na virada.
        ano, m = map(int, mes.split("-"))
        fim_mes = datetime(ano + (m == 12), m % 12 + 1, 2, tzinfo=timezone.utc)
        mes_fechado = agora >= fim_mes
        (destino / f"{mes}.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        log.info("%s: %d partidas%s", mes, len(games), "" if mes_fechado else " (mês em aberto)")
        baixados.append({"mes": mes, "completo": mes_fechado, "games": games})

    if not baixados:
        log.info("Nenhum mês novo para baixar.")
    return baixados
