"""Etapa 4 — análise por motor (Stockfish), incremental e com orçamento de tempo.

Avalia a posição inicial e a posição após cada meio-lance de cada partida e
grava em dados/analises/<usuario>/AAAA-MM.json (versionado):

    { "<uuid>": { "v": VERSAO, "prof": 12,
                  "av": [cp do ponto de vista das brancas, ...],   # n+1 posições
                  "mv": ["e2e4", ...],                              # melhor lance em cada posição
                  "pv": ["e2e4 e7e5 g1f3 b8c6", ...] } }            # linha principal (4 meios-lances)

Mate é codificado como ±(MATE - distância): +9997 = brancas dão mate em 3.
Os comentários em português são gerados depois, na publicação (comentarios.py),
então dá para mudar o texto sem rodar o motor de novo.

Sem Stockfish instalado a etapa é pulada com um aviso (a página funciona sem
análise). O GitHub Action instala o Stockfish e roda com orçamento de tempo,
das partidas mais novas para as mais antigas; o que faltar fica para o dia seguinte.
"""
import json
import logging
import os
import shutil
import time

import chess
import chess.engine

from src import config
from src.analise.tabuleiro import ler_partida

log = logging.getLogger("motor")

VERSAO = 1
MATE = 10000
PV_MEIOS_LANCES = 4
SALVAR_A_CADA = 25   # partidas — protege o progresso se o job for interrompido


def encontrar_stockfish() -> str | None:
    for candidato in (os.environ.get("STOCKFISH_PATH"), shutil.which("stockfish"), "/usr/games/stockfish"):
        if candidato and os.path.exists(candidato):
            return candidato
    return None


def dir_analises(usuario: str):
    return config.RAIZ / "dados" / "analises" / usuario


def carregar_analises(usuario: str) -> dict[str, dict]:
    """{uuid: análise} de todos os meses."""
    tudo = {}
    for arq in sorted(dir_analises(usuario).glob("*.json")):
        tudo.update(json.loads(arq.read_text(encoding="utf-8")))
    return tudo


def _codificar(score: chess.engine.PovScore) -> int:
    s = score.white()
    if s.is_mate():
        m = s.mate()
        return (MATE - abs(m)) * (1 if m > 0 else -1) if m != 0 else 0
    return max(-MATE + 100, min(MATE - 100, s.score()))


def analisar_partida(engine: chess.engine.SimpleEngine, pgn: str, limite: chess.engine.Limit) -> dict | None:
    jogo = ler_partida(pgn)
    if jogo is None:
        return None
    board = jogo.board()
    av, mv, pv = [], [], []

    def avaliar():
        if board.is_checkmate():
            # quem está na vez levou mate
            av.append(-MATE if board.turn == chess.WHITE else MATE); mv.append(""); pv.append(""); return
        if board.is_game_over(claim_draw=False):
            av.append(0); mv.append(""); pv.append(""); return
        info = engine.analyse(board, limite)
        linha = info.get("pv") or []
        av.append(_codificar(info["score"]))
        mv.append(linha[0].uci() if linha else "")
        pv.append(" ".join(m.uci() for m in linha[:PV_MEIOS_LANCES]))

    avaliar()
    for mov in jogo.mainline_moves():
        board.push(mov)
        avaliar()
    return {"v": VERSAO, "prof": limite.depth, "av": av, "mv": mv, "pv": pv}


def _gravar(usuario: str, por_mes: dict[str, dict]) -> None:
    destino = dir_analises(usuario)
    destino.mkdir(parents=True, exist_ok=True)
    for mes, analises in por_mes.items():
        arq = destino / f"{mes}.json"
        ordenado = dict(sorted(analises.items()))
        arq.write_text(json.dumps(ordenado, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def analisar(usuario: str, profundidade: int = 12, orcamento_min: float = 45) -> int:
    caminho = encontrar_stockfish()
    if not caminho:
        log.warning("Stockfish não encontrado (instale ou defina STOCKFISH_PATH); análise por motor pulada.")
        return 0

    # Partidas tratadas por mês, e análises já feitas
    por_mes_partidas = {}
    for arq in sorted(config.dir_partidas(usuario).glob("*.json")):
        por_mes_partidas[arq.stem] = json.loads(arq.read_text(encoding="utf-8")).get("partidas", [])
    por_mes_analises = {}
    for mes in por_mes_partidas:
        arq = dir_analises(usuario) / f"{mes}.json"
        por_mes_analises[mes] = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}

    pendentes = [
        (mes, p) for mes, ps in por_mes_partidas.items() for p in ps
        if (por_mes_analises[mes].get(p["uuid"]) or {}).get("v") != VERSAO
        or (por_mes_analises[mes][p["uuid"]].get("prof") or 0) < profundidade
    ]
    pendentes.sort(key=lambda x: x[1]["fim_utc"], reverse=True)   # mais novas primeiro
    if not pendentes:
        log.info("Todas as partidas já analisadas.")
        return 0
    log.info("Stockfish: %s | %d partidas pendentes | profundidade %d | orçamento %.0f min",
             caminho, len(pendentes), profundidade, orcamento_min)

    limite = chess.engine.Limit(depth=profundidade)
    fim = time.monotonic() + orcamento_min * 60
    feitas, alterados = 0, set()
    engine = chess.engine.SimpleEngine.popen_uci(caminho)
    try:
        engine.configure({"Threads": max(1, os.cpu_count() or 1), "Hash": 256})
        for mes, p in pendentes:
            if time.monotonic() > fim:
                log.info("Orçamento de tempo esgotado; %d partidas ficam para a próxima execução.", len(pendentes) - feitas)
                break
            try:
                res = analisar_partida(engine, p.get("pgn") or "", limite)
            except chess.engine.EngineError:
                log.exception("Motor falhou em %s", p["url"])
                continue
            if res is None:
                log.warning("PGN ilegível, sem análise: %s", p["url"])
                continue
            por_mes_analises[mes][p["uuid"]] = res
            alterados.add(mes)
            feitas += 1
            if feitas % SALVAR_A_CADA == 0:
                _gravar(usuario, {m: por_mes_analises[m] for m in alterados})
                log.info("… %d/%d partidas analisadas", feitas, len(pendentes))
    finally:
        engine.quit()
        _gravar(usuario, {m: por_mes_analises[m] for m in alterados})
    log.info("Análise por motor: %d partidas analisadas", feitas)
    return feitas
