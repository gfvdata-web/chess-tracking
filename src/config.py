"""Configuração central: usuário acompanhado, caminhos e logging.

O usuário vem de `config.json` na raiz; a variável de ambiente CHESS_USER
sobrescreve (útil para rodar para outra conta sem editar o arquivo).
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
    usuario = os.environ.get("CHESS_USER") or cfg.get("usuario")
    if not usuario:
        raise SystemExit("Defina 'usuario' em config.json ou a variável CHESS_USER.")
    cfg["usuario"] = usuario.strip().lower()
    cfg.setdefault("fuso_horario", "UTC")
    cfg.setdefault("user_agent", "ChessTracking/1.0")
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
