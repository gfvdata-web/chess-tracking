"""Configuração central: jogadores acompanhados, caminhos e logging.

Os jogadores vêm de `config.json` na raiz (`jogadores`: lista de
`{"usuario", "fuso_horario"?}`; o fuso de cada um cai no `fuso_horario` global
se omitido). A variável de ambiente CHESS_USER (uma ou mais contas separadas
por vírgula) restringe a execução a essas contas.
"""
import json
import logging
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_CONFIG = RAIZ / "config.json"

DIR_BRUTOS = RAIZ / "dados" / "brutos"        # JSON cru da API — não versionado
DIR_PARTIDAS = RAIZ / "dados" / "partidas"    # partidas tratadas por mês — versionado
DIR_DOCS_DADOS = RAIZ / "docs" / "dados"      # o que a página lê

API_BASE = "https://api.chess.com/pub"


def carregar() -> dict:
    cfg = json.loads(ARQUIVO_CONFIG.read_text(encoding="utf-8"))
    cfg.setdefault("fuso_horario", "UTC")
    cfg.setdefault("user_agent", "ChessTracking/1.0")
    # Formato antigo: "usuario": "conta"
    brutos = cfg.get("jogadores") or ([{"usuario": cfg["usuario"]}] if cfg.get("usuario") else [])
    jogadores = []
    for j in brutos:
        j = {"usuario": j} if isinstance(j, str) else dict(j)
        j["usuario"] = j["usuario"].strip().lower()
        j.setdefault("fuso_horario", cfg["fuso_horario"])
        jogadores.append(j)
    cfg["jogadores"] = jogadores
    so = os.environ.get("CHESS_USER")
    if so:
        cfg["selecionados"] = [u.strip().lower() for u in so.split(",") if u.strip()]
    if not jogadores and not cfg.get("selecionados"):
        raise SystemExit("Defina 'jogadores' em config.json ou a variável CHESS_USER.")
    return cfg


def dir_brutos(usuario: str) -> Path:
    return DIR_BRUTOS / usuario


def dir_partidas(usuario: str) -> Path:
    return DIR_PARTIDAS / usuario


def configurar_log(nivel=logging.INFO) -> None:
    logging.basicConfig(
        level=nivel,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
