"""Mede custo × qualidade de diferentes esforços do motor (roda no GitHub Actions).

Analisa as mesmas partidas recentes com cada limite pedido e compara com o
maior deles (a referência): tempo por partida, quantos lances mudam de
classificação, quantos erros graves da referência são encontrados e a
precisão média resultante. Não grava nada.

    python -m src.analise.medir --nos d12,250000,500000,1000000,2000000 --partidas 10

`dNN` = profundidade NN (o critério antigo); número = nós por posição.
"""
import argparse
import json
import logging
import os
import statistics
import sys
import time

import chess.engine

from src import config
from src.analise import motor
from src.analise.comentarios import LIMIARES, chance, precisao_lichess

log = logging.getLogger("medir")


def _limite(spec: str) -> chess.engine.Limit:
    return chess.engine.Limit(depth=int(spec[1:])) if spec.startswith("d") else chess.engine.Limit(nodes=int(spec))


def _classes(av: list[int]) -> list[str]:
    """Classe de cada meio-lance só pela queda na chance de quem jogou (partidas padrão: brancas começam)."""
    saida = []
    for i in range(len(av) - 1):
        antes, depois = chance(av[i]), chance(av[i + 1])
        queda = (antes - depois) if i % 2 == 0 else (depois - antes)
        saida.append(next((nome for limiar, nome in LIMIARES if queda >= limiar), ""))
    return saida


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nos", default="d12,250000,500000,1000000,2000000")
    ap.add_argument("--partidas", type=int, default=10)
    args = ap.parse_args()
    config.configurar_log()

    caminho = motor.encontrar_stockfish()
    if not caminho:
        raise SystemExit("Stockfish não encontrado.")
    todas = []
    for arq in config.DIR_PARTIDAS.glob("*/*.json"):
        todas += [p for p in json.loads(arq.read_text(encoding="utf-8")).get("partidas", [])
                  if p.get("variante", "chess") == "chess" and p.get("pgn")]
    # Mais recentes, preferindo as que têm precisão do Chess.com (revisadas lá) para comparar
    amostra = sorted(todas, key=lambda p: (p.get("precisao") is not None, p["fim_utc"]), reverse=True)[:args.partidas]
    lances = sum(p.get("meios_lances") or 0 for p in amostra)
    specs = [s.strip() for s in args.nos.split(",") if s.strip()]

    engine = motor.abrir_motor(caminho)
    log.info("Motor: %s | %d partidas (%d meios-lances) | %s CPUs",
             engine.id.get("name"), len(amostra), lances, os.cpu_count())
    resultados = {}
    try:
        for spec in specs:
            limite = _limite(spec)
            t0 = time.monotonic()
            res = []
            for p in amostra:
                engine.configure({"Clear Hash": None})
                res.append(motor.analisar_partida(engine, p["pgn"], limite))
            resultados[spec] = (time.monotonic() - t0, res)
            log.info("%s: %.1fs", spec, resultados[spec][0])
    finally:
        engine.quit()

    ref = specs[-1]
    validas = [i for i, r in enumerate(resultados[ref][1]) if r]
    ref_classes = {i: _classes(resultados[ref][1][i]["av"]) for i in validas}
    print(f"\nReferência: {ref}. Amostra: {len(amostra)} partidas, {lances} meios-lances.\n")
    print(f"{'esforço':>9} | {'s/partida':>9} | {'partidas/min':>12} | {'mesma classe':>12} | "
          f"{'graves':>6} | {'graves da ref. achados':>22} | {'precisão média':>14} | nossa × Chess.com")
    for spec in specs:
        dur, res = resultados[spec]
        iguais = total = graves = achados = graves_ref = 0
        precisoes, pares = [], []
        for i in validas:
            r, p, cref = res[i], amostra[i], ref_classes[i]
            c = _classes(r["av"])
            iguais += sum(a == b for a, b in zip(c, cref))
            total += len(cref)
            graves += c.count("erro_grave")
            graves_ref += cref.count("erro_grave")
            achados += sum(a == b == "erro_grave" for a, b in zip(c, cref))
            pr = precisao_lichess(r["av"])
            precisoes += [x for x in pr.values() if x is not None]
            eu = p["cor"] == "brancas"
            for cc, nossa in ((p.get("precisao"), pr[eu]), (p.get("precisao_adv"), pr[not eu])):
                if cc is not None and nossa is not None:
                    pares.append((nossa, cc))
        comparacao = (f"{statistics.mean(a for a, _ in pares):.1f} × {statistics.mean(b for _, b in pares):.1f} ({len(pares)} lados)"
                      if pares else "sem revisão na amostra")
        print(f"{spec:>9} | {dur / len(amostra):9.2f} | {60 * len(amostra) / dur:12.1f} | "
              f"{100 * iguais / max(1, total):11.1f}% | {graves:6d} | {achados:>10d} de {graves_ref:<9d} | "
              f"{statistics.mean(precisoes):14.1f} | {comparacao}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
