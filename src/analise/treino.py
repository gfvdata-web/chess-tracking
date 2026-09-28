"""Etapa 4 — posições de treino: onde eu cometi erro grave.

Uma posição entra no treino quando, no meu lance, a minha chance de vitória
caiu ≥ 15 pontos (erro grave) e eu ainda não estava perdido antes do lance
(chance ≥ 10%) — errar numa posição já perdida não ensina nada.

O motor (motor.py) calcula para essas posições as 3 melhores alternativas
(multipv), para o treino aceitar qualquer lance quase tão bom quanto o melhor.
"""
from src.analise.comentarios import chance

QUEDA_ERRO_GRAVE = 15    # pontos percentuais de chance de vitória
CHANCE_MINIMA = 10       # não treina posições em que eu já estava perdido
TOLERANCIA = 5           # alternativa aceita se perde no máximo 5 p.p. em relação ao melhor


def chance_de(v: int, brancas: bool) -> float:
    return chance(v) if brancas else 100 - chance(v)


def plies_de_treino(av: list[int], eu_brancas: bool, primeiro_branco: bool = True) -> list[int]:
    """Índices dos meios-lances (0-based) que viram posição de treino."""
    saida = []
    for i in range(len(av) - 1):
        brancas_jogam = (i % 2 == 0) == primeiro_branco
        if brancas_jogam != eu_brancas:
            continue
        antes = chance_de(av[i], eu_brancas)
        depois = chance_de(av[i + 1], eu_brancas)
        if antes - depois >= QUEDA_ERRO_GRAVE and antes >= CHANCE_MINIMA:
            saida.append(i)
    return saida
