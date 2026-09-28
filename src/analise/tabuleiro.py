"""Etapa 4 — reprodução das partidas no tabuleiro (python-chess, sem motor).

Para cada partida: lances (SAN/UCI), posição após cada meio-lance, saldo de
material ao longo da partida e fatos usados nos "padrões de vitória e derrota"
da página (virada, vantagem desperdiçada, dama perdida, roque, tipo de mate).
"""
import io
import logging

import chess
import chess.pgn

log = logging.getLogger("tabuleiro")

VALOR = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
NOME_PECA = {chess.PAWN: "peao", chess.KNIGHT: "cavalo", chess.BISHOP: "bispo",
             chess.ROOK: "torre", chess.QUEEN: "dama", chess.KING: "rei"}
LIMIAR_MATERIAL = 3      # pontos de material que contam como "vantagem clara"
JANELA_ESTAVEL = 3       # o saldo precisa se manter por 3 meios-lances (ignora trocas em andamento)


def material(board: chess.Board, cor: bool) -> int:
    return sum(VALOR[p.piece_type] for p in board.piece_map().values() if p.color == cor)


def ler_partida(pgn: str) -> chess.pgn.Game | None:
    try:
        jogo = chess.pgn.read_game(io.StringIO(pgn))
    except Exception:
        return None
    if jogo is None or jogo.errors:
        return None
    return jogo


def _tipo_mate(board: chess.Board, lances_completos: int) -> tuple[str | None, str | None]:
    """Posição final de mate -> (peça que deu mate, tipo)."""
    if not board.is_checkmate():
        return None, None
    ultimo = board.peek()
    peca = board.piece_at(ultimo.to_square)
    peca_nome = NOME_PECA[peca.piece_type] if peca else None
    rei = board.king(board.turn)
    atacantes = list(board.checkers())
    vizinhas = [sq for sq in chess.SQUARES if chess.square_distance(sq, rei) == 1]

    if lances_completos <= 8 and peca and peca.piece_type == chess.QUEEN and ultimo.to_square in (chess.F7, chess.F2):
        return peca_nome, "pastor"
    if len(atacantes) == 1 and board.piece_type_at(atacantes[0]) == chess.KNIGHT and \
            all(board.color_at(sq) == board.turn for sq in vizinhas):
        return peca_nome, "afogado"
    fileira_fundo = 0 if board.turn == chess.WHITE else 7
    if chess.square_rank(rei) == fileira_fundo and any(
            board.piece_type_at(a) in (chess.ROOK, chess.QUEEN) and chess.square_rank(a) == fileira_fundo
            for a in atacantes):
        return peca_nome, "corredor"
    if lances_completos <= 15:
        return peca_nome, "rapido"
    return peca_nome, "outro"


def _dama_perdida(capturas: list[tuple[int, bool, int]], cor: bool) -> int | None:
    """Lance (número) em que a dama de `cor` foi capturada sem que a dama adversária
    caísse nos 2 meios-lances seguintes (troca de damas não conta)."""
    for i, (ply, cor_capturada, tipo) in enumerate(capturas):
        if tipo == chess.QUEEN and cor_capturada == cor:
            troca = any(c[1] != cor and c[2] == chess.QUEEN and 0 < c[0] - ply <= 2 for c in capturas[i + 1:])
            if not troca:
                return ply // 2 + 1
    return None


def reproduzir(p: dict) -> dict | None:
    """Reproduz a partida. Retorna None se o PGN não puder ser lido."""
    jogo = ler_partida(p.get("pgn") or "")
    if jogo is None:
        return None
    eu = chess.WHITE if p["cor"] == "brancas" else chess.BLACK
    board = jogo.board()
    fen_inicial = board.board_fen()
    fen_inicial_completa = board.fen()

    san, uci, fens, saldo, capturas = [], [], [], [], []
    roque = {chess.WHITE: None, chess.BLACK: None}
    for ply, mov in enumerate(jogo.mainline_moves()):
        cor = board.turn
        if board.is_castling(mov) and roque[cor] is None:
            roque[cor] = "curto" if chess.square_file(mov.to_square) > chess.square_file(mov.from_square) else "longo"
        if board.is_capture(mov):
            alvo = mov.to_square
            if board.is_en_passant(mov):
                alvo = mov.to_square + (-8 if cor == chess.WHITE else 8)
            capturada = board.piece_at(alvo)
            if capturada:
                capturas.append((ply, capturada.color, capturada.piece_type))
        san.append(board.san(mov))
        uci.append(mov.uci())
        board.push(mov)
        fens.append(board.board_fen())
        saldo.append(material(board, eu) - material(board, not eu))

    n = len(saldo)
    janela = min(JANELA_ESTAVEL, n) or 1
    estaveis_min = [max(saldo[i:i + janela]) for i in range(max(0, n - janela + 1))]   # pior saldo que se sustentou
    estaveis_max = [min(saldo[i:i + janela]) for i in range(max(0, n - janela + 1))]   # melhor saldo que se sustentou
    lances_completos = (n + 1) // 2
    mate_peca, mate_tipo = _tipo_mate(board, lances_completos)

    # Lance a partir do qual fiquei com ≥3 a menos e nunca mais recuperei
    colapso = None
    for i in range(n):
        if all(s <= -LIMIAR_MATERIAL for s in saldo[i:]) and n - i >= 1:
            colapso = i // 2 + 1
            break

    return {
        "fen_inicial": fen_inicial, "fen_inicial_completa": fen_inicial_completa,
        "chess960": board.chess960,
        "san": san, "uci": uci, "fens": fens, "saldo": saldo,
        "fatos": {
            "roque": roque[eu] or "", "adv_roque": roque[not eu] or "",
            "min_saldo": min(estaveis_min) if estaveis_min else 0,
            "max_saldo": max(estaveis_max) if estaveis_max else 0,
            "saldo_final": saldo[-1] if saldo else 0,
            "perdi_dama": _dama_perdida(capturas, eu),
            "adv_perdeu_dama": _dama_perdida(capturas, not eu),
            "mate_peca": mate_peca, "mate_tipo": mate_tipo,
            "colapso": colapso,
        },
    }
