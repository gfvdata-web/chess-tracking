"""Orquestra o pipeline: coleta (2) -> tratamento (3) -> análise por motor (4, opcional) -> publicação (5).

Uso:
    python run_pipeline.py                # incremental: só meses novos + mês corrente
    python run_pipeline.py --completo     # rebaixa e retrata todo o histórico
    python run_pipeline.py --sem-coleta   # retrata a partir de dados/brutos/, sem chamar a API
    python run_pipeline.py --analisar --orcamento-min 45   # + Stockfish nas partidas ainda não analisadas
    python run_pipeline.py --usuario maherculano           # só uma conta (ou CHESS_USER=conta1,conta2)

Roda para cada jogador de config.json. O orçamento do Stockfish é repartido:
cada jogador recebe o tempo restante dividido pelos jogadores que faltam, então
o que um não usa passa para o seguinte.
"""
import argparse
import json
import logging
import sys
import time

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
    ap.add_argument("--orcamento-min", type=float, default=45, help="tempo total de análise, em minutos")
    ap.add_argument("--usuario", action="append", help="roda só para esta conta (pode repetir)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    config.configurar_log(logging.DEBUG if args.verbose else logging.INFO)
    cfg = config.carregar()
    todos = cfg["jogadores"]
    selecionados = [u.strip().lower() for u in args.usuario] if args.usuario else cfg.get("selecionados")
    if selecionados:
        conhecidos = {j["usuario"]: j for j in todos}
        jogadores = [conhecidos.get(u) or {"usuario": u, "fuso_horario": cfg["fuso_horario"]} for u in selecionados]
    else:
        jogadores = todos
    log.info("Jogadores: %s", ", ".join(j["usuario"] for j in jogadores))

    cliente = None if args.sem_coleta else chesscom.ClienteChessCom(cfg["user_agent"])
    falhas = 0
    for j in jogadores:
        usuario = j["usuario"]
        log.info("== %s (fuso %s) ==", usuario, j["fuso_horario"])
        try:
            if args.sem_coleta:
                baixados = partidas.carregar_brutos(usuario)
            else:
                gravar_perfil(usuario, chesscom.coletar_perfil(cliente, usuario))
                baixados = chesscom.coletar_partidas(cliente, usuario, completo=args.completo)
            partidas.tratar(usuario, j["fuso_horario"], baixados)
        except chesscom.ErroAPI as e:
            # Um jogador com problema (conta fechada, API fora) não impede os demais
            log.error("Erro na API do Chess.com para %s: %s", usuario, e)
            falhas += 1

    if args.analisar:
        fim = time.monotonic() + args.orcamento_min * 60
        for i, j in enumerate(jogadores):
            restante = max(0.0, (fim - time.monotonic()) / 60)
            fatia = restante / (len(jogadores) - i)
            if fatia < 0.5:
                log.info("Orçamento do motor esgotado antes de %s.", j["usuario"])
                break
            log.info("Motor para %s: %.1f min", j["usuario"], fatia)
            motor.analisar(j["usuario"], args.profundidade, fatia)

    mudou = False
    for j in jogadores:
        mudou |= painel.publicar(j["usuario"], j["fuso_horario"])
    # O índice sempre lista todos os jogadores do config.json
    painel.publicar_indice([j["usuario"] for j in todos], mudou)
    return 1 if falhas == len(jogadores) else 0


if __name__ == "__main__":
    sys.exit(main())
