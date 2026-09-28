"""Etapa 4 — análise por motor (Stockfish), incremental e com orçamento de tempo.

Avalia a posição inicial e a posição após cada meio-lance de cada partida e
grava em dados/analises/<usuario>/AAAA-MM.json (versionado):

    { "<uuid>": { "v": VERSAO, "nos": 250000, "motor": "Stockfish 19",
                  "av": [cp do ponto de vista das brancas, ...],   # n+1 posições
                  "mv": ["e2e4", ...],                              # melhor lance em cada posição
                  "pv": ["e2e4 e7e5 g1f3 b8c6", ...],               # linha principal (4 meios-lances)
                  "alt_v": 1, "alt": { "<ply>": [["h6h5", -180], ...] } } }   # 3 melhores lances nas posições de treino

Mate é codificado como ±(MATE - distância): +9997 = brancas dão mate em 3.
Os comentários em português são gerados depois, na publicação (comentarios.py),
então dá para mudar o texto sem rodar o motor de novo.

O esforço por posição é um limite de nós (posições calculadas), não de
profundidade: o custo fica previsível — profundidade fixa é instantânea na
abertura e cara no meio-jogo — e é o mesmo critério da análise do Lichess.
Análises feitas com menos nós (ou com profundidade, formato antigo) são refeitas.

Sem Stockfish instalado a etapa é pulada com um aviso (a página funciona sem
análise). O GitHub Action baixa o Stockfish oficial (versão fixada no workflow)
e roda com orçamento de tempo, das partidas mais novas para as mais antigas;
o que faltar fica para o dia seguinte.
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
NOS_PADRAO = 250_000   # nós por posição — medido em 2026-09-28: ver CONTEXTO.md
ALT_VERSAO = 2
MULTIPV = 3          # alternativas por posição de treino (mesmo limite de nós)


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


def abrir_motor(caminho: str) -> chess.engine.SimpleEngine:
    engine = chess.engine.SimpleEngine.popen_uci(caminho)
    engine.configure({"Threads": max(1, os.cpu_count() or 1), "Hash": 256})
    return engine


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
    return {"v": VERSAO, "nos": limite.nodes, "motor": engine.id.get("name", ""), "av": av, "mv": mv, "pv": pv}


def _gravar(usuario: str, por_mes: dict[str, dict]) -> None:
    destino = dir_analises(usuario)
    destino.mkdir(parents=True, exist_ok=True)
    for mes, analises in por_mes.items():
        arq = destino / f"{mes}.json"
        ordenado = dict(sorted(analises.items()))
        arq.write_text(json.dumps(ordenado, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")




def alternativas_partida(engine: chess.engine.SimpleEngine, p: dict, an: dict, limite: chess.engine.Limit) -> dict:
    """Para cada posição de treino da partida, as 3 melhores jogadas: {ply: [[uci, cp_brancas], ...]}."""
    from src.analise.treino import plies_de_treino   # import local: treino -> comentarios -> motor

    jogo = ler_partida(p.get("pgn") or "")
    if jogo is None:
        return {}
    board = jogo.board()
    alvos = set(plies_de_treino(an["av"], p["cor"] == "brancas", board.turn == chess.WHITE))
    saida = {}
    for i, mov in enumerate(jogo.mainline_moves()):
        if i in alvos:
            infos = engine.analyse(board, limite, multipv=MULTIPV)
            saida[str(i)] = [[info["pv"][0].uci(), _codificar(info["score"])] for info in infos if info.get("pv")]
        board.push(mov)
    return saida


def analisar(usuario: str, nos: int = NOS_PADRAO, orcamento_min: float = 45) -> int:
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

    def precisa_principal(mes, p):
        an = por_mes_analises[mes].get(p["uuid"]) or {}
        return an.get("v") != VERSAO or (an.get("nos") or 0) < nos

    def precisa_alternativas(mes, p):
        an = por_mes_analises[mes].get(p["uuid"]) or {}
        return bool(an) and an.get("alt_v") != ALT_VERSAO and p.get("variante", "chess") == "chess"

    mais_novas = lambda lst: sorted(lst, key=lambda x: x[1]["fim_utc"], reverse=True)
    pendentes = mais_novas([(m, p) for m, ps in por_mes_partidas.items() for p in ps if precisa_principal(m, p)])
    if not pendentes and not any(precisa_alternativas(m, p) for m, ps in por_mes_partidas.items() for p in ps):
        log.info("Todas as partidas já analisadas (incluindo as posições de treino).")
        return 0
    log.info("Stockfish: %s | %d partidas pendentes | %d nós por posição | orçamento %.0f min",
             caminho, len(pendentes), nos, orcamento_min)

    fim = time.monotonic() + orcamento_min * 60
    feitas, feitas_alt, alterados = 0, 0, set()
    engine = abrir_motor(caminho)
    log.info("Motor: %s", engine.id.get("name", "?"))

    def reabrir_se_morreu():
        # O Stockfish 19 encerra o processo diante de posição/comando inválido;
        # sem reabrir, todas as partidas seguintes falhariam.
        nonlocal engine
        try:
            engine.ping()
        except chess.engine.EngineError:
            log.warning("Motor encerrado; reabrindo.")
            try:
                engine.quit()
            except Exception:
                pass
            engine = abrir_motor(caminho)

    try:
        # 1) Avaliação lance a lance das partidas pendentes
        limite = chess.engine.Limit(nodes=nos)
        for mes, p in pendentes:
            if time.monotonic() > fim:
                log.info("Orçamento de tempo esgotado; %d partidas ficam para a próxima execução.", len(pendentes) - feitas)
                break
            try:
                res = analisar_partida(engine, p.get("pgn") or "", limite)
            except chess.engine.EngineError:
                log.exception("Motor falhou em %s", p["url"])
                reabrir_se_morreu()
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

        # 2) Alternativas (multipv) nas posições de treino — depois da análise principal
        pend_alt = mais_novas([(m, p) for m, ps in por_mes_partidas.items() for p in ps if precisa_alternativas(m, p)])
        if pend_alt and time.monotonic() < fim:
            log.info("Posições de treino: %d partidas com alternativas pendentes (multipv %d, %d nós)",
                     len(pend_alt), MULTIPV, nos)
        for mes, p in pend_alt:
            if time.monotonic() > fim:
                log.info("Orçamento esgotado; alternativas de %d partidas ficam para a próxima execução.", len(pend_alt) - feitas_alt)
                break
            an = por_mes_analises[mes][p["uuid"]]
            try:
                an["alt"] = alternativas_partida(engine, p, an, limite)
            except chess.engine.EngineError:
                log.exception("Motor falhou (alternativas) em %s", p["url"])
                reabrir_se_morreu()
                continue
            an["alt_v"] = ALT_VERSAO
            alterados.add(mes)
            feitas_alt += 1
            if feitas_alt % (SALVAR_A_CADA * 4) == 0:
                _gravar(usuario, {m: por_mes_analises[m] for m in alterados})
                log.info("… alternativas de %d/%d partidas", feitas_alt, len(pend_alt))
    finally:
        engine.quit()
        _gravar(usuario, {m: por_mes_analises[m] for m in alterados})
    log.info("Análise por motor: %d partidas analisadas; alternativas de treino em %d partidas", feitas, feitas_alt)
    return feitas
