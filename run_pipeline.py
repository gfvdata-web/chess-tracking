"""Orquestra o pipeline: coleta (2) -> tratamento (3) -> análise por motor (4, opcional) -> publicação (5).

Uso:
    python run_pipeline.py                # incremental: só meses novos + mês corrente
    python run_pipeline.py --completo     # rebaixa e retrata todo o histórico
    python run_pipeline.py --sem-coleta   # retrata a partir de dados/brutos/, sem chamar a API
    python run_pipeline.py --analisar --orcamento-min 45   # + Stockfish nas partidas ainda não analisadas
    CHESS_USER=outra_conta python run_pipeline.py
"""
import argparse
import json
import logging
import sys

from src import config
from src.coleta import chesscom
from src.analise import motor
from src.publicacao import painel
from src.tratamento import partidas

log = logging.getLogger("pipeline")

# Campos do perfil que mudam sem haver partida nova — ficam fora para não gerar commit diário à toa
CAMPOS_VOLATEIS_PERFIL = {"last_online", "followers"}


def gravar_perfil(usuario: str, dados: dict) -> None:
    perfil = {k: v for k, v in dados["perfil"].items() if k not in CAMPOS_VOLATEIS_PERFIL}
    stats = {k: v for k, v in dados["stats"].items() if k.startswith("chess")}
    arq = config.RAIZ / "dados" / "perfil" / f"{usuario}.json"
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps({"perfil": perfil, "stats": stats}, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--completo", action="store_true", help="rebaixa todos os meses")
    ap.add_argument("--sem-coleta", action="store_true", help="não chama a API; usa dados/brutos/")
    ap.add_argument("--analisar", action="store_true", help="analisa com Stockfish as partidas pendentes")
    ap.add_argument("--profundidade", type=int, default=12, help="profundidade do motor (padrão 12)")
    ap.add_argument("--orcamento-min", type=float, default=45, help="tempo máximo de análise, em minutos")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    config.configurar_log(logging.DEBUG if args.verbose else logging.INFO)
    cfg = config.carregar()
    usuario = cfg["usuario"]
    log.info("Usuário: %s | fuso: %s", usuario, cfg["fuso_horario"])

    try:
        if args.sem_coleta:
            baixados = partidas.carregar_brutos(usuario)
        else:
            cliente = chesscom.ClienteChessCom(cfg["user_agent"])
            gravar_perfil(usuario, chesscom.coletar_perfil(cliente, usuario))
            baixados = chesscom.coletar_partidas(cliente, usuario, completo=args.completo)
        partidas.tratar(usuario, cfg["fuso_horario"], baixados)
    except chesscom.ErroAPI as e:
        log.error("Erro na API do Chess.com: %s", e)
        return 1

    if args.analisar:
        motor.analisar(usuario, args.profundidade, args.orcamento_min)
    painel.publicar(usuario, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
