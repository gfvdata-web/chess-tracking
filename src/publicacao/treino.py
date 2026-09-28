"""Etapa 5 — posições de treino -> docs/dados/treino.json.

Para cada erro grave meu (critério em src/analise/treino.py), grava a posição
antes do lance, os lances legais (para o tabuleiro só aceitar jogadas válidas),
o lance da partida, o melhor lance, as alternativas aceitas e o contexto.
"""
import chess

from src.analise.comentarios import fmt_aval
from src.analise.treino import TOLERANCIA, chance_de, plies_de_treino


def _fase(ply: int) -> str:
    lance = ply // 2 + 1
    return "abertura" if lance <= 10 else "meio" if lance <= 25 else "final"


def _dests(board: chess.Board) -> dict[str, str]:
    """{'e2': 'e3e4', ...} — casas de destino por casa de origem."""
    d: dict[str, list[str]] = {}
    for m in board.legal_moves:
        orig, dest = chess.square_name(m.from_square), chess.square_name(m.to_square)
        if dest not in d.setdefault(orig, []):
            d[orig].append(dest)
    return {k: "".join(v) for k, v in d.items()}


def _san_linha(board: chess.Board, ucis: list[str]) -> list[str]:
    b, sans = board.copy(stack=False), []
    for u in ucis:
        try:
            m = chess.Move.from_uci(u)
        except ValueError:
            break
        if m not in b.legal_moves:
            break
        sans.append(b.san(m))
        b.push(m)
    return sans


def extrair(p: dict, mes: str, rep: dict, com: dict, an: dict) -> list[dict]:
    if p.get("variante", "chess") != "chess" or rep.get("chess960"):
        return []
    eu_brancas = p["cor"] == "brancas"
    board = chess.Board(rep["fen_inicial_completa"])
    alvos = set(plies_de_treino(an["av"], eu_brancas, board.turn == chess.WHITE))
    if not alvos:
        return []
    alt = an.get("alt") or {}
    saida = []
    for i, u in enumerate(rep["uci"]):
        if i in alvos and an["mv"][i]:
            melhor_uci = an["mv"][i]
            try:
                melhor = chess.Move.from_uci(melhor_uci)
            except ValueError:
                melhor = None
            if melhor is None or melhor not in board.legal_moves:
                board.push_uci(u)
                continue
            # Aceitas: o melhor lance + alternativas do multipv que perdem ≤ TOLERANCIA
            opcoes = alt.get(str(i)) or []
            ref = chance_de(opcoes[0][1], eu_brancas) if opcoes else None
            aceitos = [melhor_uci] + [uci for uci, cp in opcoes
                                      if uci != melhor_uci and uci != u and ref is not None
                                      and chance_de(cp, eu_brancas) >= ref - TOLERANCIA]
            depois_melhor = board.copy(stack=False)
            depois_melhor.push(melhor)
            sinal = 1 if eu_brancas else -1
            saida.append({
                "id": f"{p['uuid']}:{i}", "uuid": p["uuid"], "mes": mes, "ply": i,
                "num": f"{i // 2 + 1}{'.' if i % 2 == 0 else '…'}",
                "fen": board.fen(), "cor": "white" if eu_brancas else "black",
                "ult": rep["uci"][i - 1] if i else None, "xeque": board.is_check(),
                "dests": _dests(board),
                "jogado": rep["san"][i], "jogado_uci": u,
                "melhor": board.san(melhor), "melhor_uci": melhor_uci,
                "aceitos": aceitos,
                "aceitos_san": [board.san(chess.Move.from_uci(x)) for x in aceitos],
                "linha": _san_linha(board, (an["pv"][i] or "").split()),
                "fen_sol": depois_melhor.board_fen(),
                "antes": fmt_aval(an["av"][i] * sinal), "depois": fmt_aval(an["av"][i + 1] * sinal),
                "chance_antes": round(chance_de(an["av"][i], eu_brancas)),
                "chance_depois": round(chance_de(an["av"][i + 1], eu_brancas)),
                "motivo": com["comentarios"][i] if com else "",
                "fase": _fase(i), "ritmo": p["ritmo"], "controle": p["controle"],
                "data": p["data_local"], "adversario": p["adversario"], "adv_rating": p["adv_rating"],
                "meu_rating": p["meu_rating"], "abertura": p["abertura"], "resultado": p["resultado"],
            })
        board.push_uci(u)
    return saida
