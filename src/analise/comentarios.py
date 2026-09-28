"""Etapa 4 — comentários lance a lance a partir da análise do motor.

Classificação pela queda na chance de vitória de quem jogou (fórmula do Lichess):
imprecisão ≥ 5 pontos percentuais, erro ≥ 10, erro grave ≥ 15. A precisão
estimada por lance também segue o Lichess (103,17·e^(−0,0435·queda) − 3,17).
"""
import math

import chess

from src.analise.motor import MATE
from src.analise.tabuleiro import NOME_PECA, VALOR, material

LIMIARES = ((15, "erro_grave"), (10, "erro"), (5, "imprecisao"))
ROTULO = {"erro_grave": "Erro grave", "erro": "Erro", "imprecisao": "Imprecisão", "melhor": "Melhor lance"}
ARTIGO_PECA = {"peao": "um peão", "cavalo": "um cavalo", "bispo": "um bispo", "torre": "uma torre", "dama": "a dama"}


def eh_mate(v: int) -> bool:
    return abs(v) > MATE - 1000


def chance(v: int) -> float:
    """Avaliação (cp, brancas) -> chance de vitória das brancas em % (0–100)."""
    if eh_mate(v):
        return 100.0 if v > 0 else 0.0
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * v)) - 1)


def fmt_aval(v: int) -> str:
    if eh_mate(v):
        n = MATE - abs(v)
        return ("#" if v > 0 else "#-") + str(n) if n else ("1-0" if v > 0 else "0-1")
    return f"{v / 100:+.1f}".replace(".", ",")


def _san_linha(board: chess.Board, ucis: list[str], limite: int) -> list[str]:
    b, sans = board.copy(stack=False), []
    for u in ucis[:limite]:
        try:
            m = chess.Move.from_uci(u)
            if m not in b.legal_moves:
                break
            sans.append(b.san(m))
            b.push(m)
        except ValueError:
            break
    return sans


def _perda_na_linha(board: chess.Board, ucis: list[str], cor: bool) -> int:
    """Quanto material `cor` perde ao fim da linha do motor (≥ 0). Medir só no fim
    evita contar como perda a captura que ainda vai ser retomada."""
    b = board.copy(stack=False)
    inicio = material(b, cor) - material(b, not cor)
    for u in ucis:
        try:
            m = chess.Move.from_uci(u)
        except ValueError:
            break
        if m not in b.legal_moves:
            break
        b.push(m)
    return max(0, inicio - (material(b, cor) - material(b, not cor)))


def precisao_lichess(av: list[int], primeiro_branco: bool = True) -> dict[bool, float | None]:
    """Precisão por cor como no Lichess: média (ponderada pela volatilidade da
    posição) e média harmônica da precisão de cada lance, tiradas as duas pela média.
    Retorna {True: brancas, False: pretas}."""
    wp = [chance(v) for v in av]
    if len(wp) < 2:
        return {True: None, False: None}
    janela = max(2, min(8, len(wp) // 10))
    janelas = [wp[:janela]] * (min(janela, len(wp)) - 2) + [wp[i:i + janela] for i in range(len(wp) - janela + 1)]

    def desvio(xs):
        m = sum(xs) / len(xs)
        return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))

    pesos = [max(0.5, min(12.0, desvio(j))) for j in janelas]
    por_cor = {True: [], False: []}
    for i in range(len(wp) - 1):
        brancas = (i % 2 == 0) == primeiro_branco
        antes, depois = (wp[i], wp[i + 1]) if brancas else (100 - wp[i], 100 - wp[i + 1])
        if depois >= antes:
            acc = 100.0
        else:
            acc = max(0.0, min(100.0, 103.1668100711649 * math.exp(-0.04354415386753951 * (antes - depois)) - 3.166924740191411 + 1))
        por_cor[brancas].append((acc, pesos[i] if i < len(pesos) else pesos[-1]))

    def combinar(itens):
        if not itens:
            return None
        ponderada = sum(a * w for a, w in itens) / sum(w for _, w in itens)
        harmonica = len(itens) / sum(1 / max(a, 0.001) for a, _ in itens)
        return round((ponderada + harmonica) / 2, 1)

    return {True: combinar(por_cor[True]), False: combinar(por_cor[False])}


def comentar(fen_inicial_completa: str, ucis: list[str], analise: dict, eu_brancas: bool, chess960: bool = False) -> dict:
    """Retorna {classes, comentarios, melhores (SAN), resumo}."""
    av, mv, pv = analise["av"], analise["mv"], analise["pv"]
    board = chess.Board(fen_inicial_completa, chess960=chess960)
    classes, comentarios, melhores = [], [], []
    contagem = {c: {"imprecisao": 0, "erro": 0, "erro_grave": 0} for c in (True, False)}
    primeiro_grave = {True: None, False: None}
    maior_queda = {True: (0, None), False: (0, None)}

    for i, u in enumerate(ucis):
        cor = board.turn
        sinal = 1 if cor == chess.WHITE else -1
        antes, depois = av[i], av[i + 1]
        cv_antes = chance(antes) if cor == chess.WHITE else 100 - chance(antes)
        cv_depois = chance(depois) if cor == chess.WHITE else 100 - chance(depois)
        queda = max(0.0, cv_antes - cv_depois)

        mov = chess.Move.from_uci(u)
        melhor_uci = mv[i]
        melhor_san = ""
        if melhor_uci:
            try:
                bm = chess.Move.from_uci(melhor_uci)
                melhor_san = board.san(bm) if bm in board.legal_moves else ""
            except ValueError:
                pass
        melhores.append(melhor_san)

        classe = ""
        for limiar, nome in LIMIARES:
            if queda >= limiar:
                classe = nome
                break
        tinha_mate = eh_mate(antes) and antes * sinal > 0
        ainda_mate = eh_mate(depois) and depois * sinal > 0
        if not classe and tinha_mate and not ainda_mate:
            classe = "imprecisao"
        if not classe and u == melhor_uci:
            classe = "melhor"

        texto = []
        board_antes = board.copy(stack=False)
        board.push(mov)
        if board.is_checkmate():
            texto.append("Xeque-mate.")
        elif classe in ("erro_grave", "erro", "imprecisao"):
            contagem[cor][classe] += 1
            numero = i // 2 + 1
            if classe == "erro_grave" and primeiro_grave[cor] is None:
                primeiro_grave[cor] = numero
            if queda > maior_queda[cor][0]:
                maior_queda[cor] = (queda, i)
            motivo = ""
            adv_mate = eh_mate(depois) and depois * sinal < 0
            if adv_mate:
                motivo = f"Permite mate em {MATE - abs(depois)}."
            elif tinha_mate and not ainda_mate:
                motivo = f"Havia mate em {MATE - abs(antes)}."
            else:
                linha_adv = pv[i + 1].split() if pv[i + 1] else []
                perda = _perda_na_linha(board, linha_adv, cor)
                if perda >= 2 and linha_adv:
                    resposta = _san_linha(board, linha_adv, 1)
                    motivo = f"Perde material depois de {resposta[0]}." if resposta else "Perde material."
                elif melhor_uci and board_antes.is_capture(chess.Move.from_uci(melhor_uci)) and not board_antes.is_capture(mov):
                    alvo = board_antes.piece_at(chess.Move.from_uci(melhor_uci).to_square)
                    if alvo and VALOR[alvo.piece_type] >= 3:
                        motivo = f"Deixou de capturar {ARTIGO_PECA[NOME_PECA[alvo.piece_type]]}."
            if motivo:
                texto.append(motivo)
            if melhor_san and u != melhor_uci:
                texto.append(f"Melhor era {melhor_san}.")
            texto.append(f"Avaliação para quem jogou: {fmt_aval(antes * sinal)} → {fmt_aval(depois * sinal)}.")
        classes.append(classe)
        comentarios.append(" ".join(texto))

    precisao = precisao_lichess(av, primeiro_branco=chess.Board(fen_inicial_completa).turn == chess.WHITE)
    eu, adv = (True, False) if eu_brancas else (False, True)
    decisivo = maior_queda[eu][1] if maior_queda[eu][0] >= 15 else None
    return {
        "classes": classes,
        "comentarios": comentarios,
        "melhores": melhores,
        "resumo": {
            "precisao": precisao[eu], "precisao_adv": precisao[adv],
            "meus": contagem[eu], "adv": contagem[adv],
            "primeiro_erro_grave": primeiro_grave[eu], "adv_primeiro_erro_grave": primeiro_grave[adv],
            "lance_decisivo": decisivo,   # índice do meio-lance em que mais perdi
        },
    }
