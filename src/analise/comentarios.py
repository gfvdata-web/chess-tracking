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


def comentar(fen_inicial_completa: str, ucis: list[str], analise: dict, eu_brancas: bool, chess960: bool = False) -> dict:
    """Retorna {classes, comentarios, melhores (SAN), resumo}."""
    av, mv, pv = analise["av"], analise["mv"], analise["pv"]
    board = chess.Board(fen_inicial_completa, chess960=chess960)
    classes, comentarios, melhores = [], [], []
    quedas = {True: [], False: []}          # por cor (True = brancas)
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
        quedas[cor].append(queda)

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
                    resposta = _san_linha(board, linha_adv, 2)
                    motivo = f"Perde material: o adversário responde {' '.join(resposta)}." if resposta else "Perde material."
                elif melhor_uci and board_antes.is_capture(chess.Move.from_uci(melhor_uci)) and not board_antes.is_capture(mov):
                    alvo = board_antes.piece_at(chess.Move.from_uci(melhor_uci).to_square)
                    if alvo and VALOR[alvo.piece_type] >= 3:
                        motivo = f"Deixou de capturar {ARTIGO_PECA[NOME_PECA[alvo.piece_type]]}."
            texto.append(f"{ROTULO[classe]}. {motivo}".strip())
            if melhor_san and u != melhor_uci:
                texto.append(f"Melhor era {melhor_san}.")
            texto.append(f"Avaliação {fmt_aval(antes)} → {fmt_aval(depois)}.")
        elif classe == "melhor" and i >= 8 and abs(chance(antes) - 50) < 45:
            texto.append("Melhor lance.")
        classes.append(classe)
        comentarios.append(" ".join(texto))

    def precisao(qs):
        if not qs:
            return None
        return round(sum(max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * q) - 3.1669)) for q in qs) / len(qs), 1)

    eu, adv = (True, False) if eu_brancas else (False, True)
    decisivo = maior_queda[eu][1] if maior_queda[eu][0] >= 15 else None
    return {
        "classes": classes,
        "comentarios": comentarios,
        "melhores": melhores,
        "resumo": {
            "precisao": precisao(quedas[eu]), "precisao_adv": precisao(quedas[adv]),
            "meus": contagem[eu], "adv": contagem[adv],
            "primeiro_erro_grave": primeiro_grave[eu], "adv_primeiro_erro_grave": primeiro_grave[adv],
            "lance_decisivo": decisivo,   # índice do meio-lance em que mais perdi
        },
    }
