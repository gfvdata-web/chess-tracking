"""Etapa 5 — publicação: partidas tratadas -> JSON que a página lê.

Gera em docs/dados/<usuario>/:
- partidas.json      tabela colunar (sem PGN), uma linha por partida, com métricas
                     de gestão de tempo, fatos de tabuleiro (padrões) e o resumo
                     da análise por motor quando existir;
- jogos/AAAA-MM.json lances, posições, relógio, saldo de material e — se a partida
                     foi analisada — avaliação, classificação e comentário de cada
                     lance. A página carrega o mês só quando uma partida é aberta;
- perfil.json        perfil, ratings atuais/recordes e metadados;
- treino.json        posições dos erros graves (ver src/publicacao/treino.py).

E, uma vez por execução, em docs/dados/:
- jogadores.json     índice dos jogadores (nome, avatar, ratings, totais) para o seletor;
- gerado.json        carimbo da última geração com mudança.
"""
import json
import logging
import shutil
from datetime import datetime, timezone
from statistics import mean

from src import config
from src.analise import comentarios, motor, tabuleiro
from src.publicacao import treino

log = logging.getLogger("publicacao")

COLUNAS = [
    "uuid", "mes", "url", "fim", "data", "hora", "dia_semana", "ritmo", "controle", "variante", "ranqueada",
    "cor", "adversario", "meu_rating", "adv_rating", "resultado", "motivo", "eco", "abertura",
    "familia", "lances", "precisao", "precisao_adv",
    # gestão de tempo (null em daily ou sem relógio)
    "t_abertura", "t_meio", "t_final", "relogio_final", "adv_relogio_final", "apuro",
    # fatos de tabuleiro (padrões)
    "roque", "adv_roque", "min_saldo", "max_saldo", "saldo_final", "perdi_dama", "adv_perdeu_dama",
    "mate_peca", "mate_tipo", "colapso",
    # análise por motor (null se a partida ainda não foi analisada)
    "precisao_motor", "precisao_motor_adv", "imprecisoes", "erros", "erros_graves",
    "adv_erros_graves", "primeiro_erro_grave", "adv_primeiro_erro_grave",
]

FASES = ((1, 10), (11, 25), (26, 10_000))   # lances meus: abertura, meio-jogo, final
LIMIAR_APURO = 0.10                          # ficou com < 10% do tempo-base em algum momento


def _controle(controle: str | None) -> tuple[float, float] | None:
    """'600+5' -> (600, 5); '180' -> (180, 0); daily ('1/86400') -> None."""
    if not controle or "/" in controle:
        return None
    base, _, inc = controle.partition("+")
    try:
        return float(base), float(inc or 0)
    except ValueError:
        return None


def metricas_tempo(p: dict) -> dict:
    vazio = {"t_abertura": None, "t_meio": None, "t_final": None,
             "relogio_final": None, "adv_relogio_final": None, "apuro": None}
    ctrl = _controle(p.get("controle"))
    rel = p.get("relogios") or []
    if not ctrl or not rel or p.get("ritmo") == "daily":
        return vazio
    base, inc = ctrl
    meu = 0 if p["cor"] == "brancas" else 1
    meus = rel[meu::2]
    advs = rel[1 - meu::2]
    if not meus:
        return vazio

    gastos, anterior = [], base
    for r in meus:
        gastos.append(max(0.0, anterior - r + inc))
        anterior = r

    def media_fase(ini, fim):
        trecho = gastos[ini - 1:fim]
        return round(mean(trecho), 1) if trecho else None

    return {
        "t_abertura": media_fase(*FASES[0]),
        "t_meio": media_fase(*FASES[1]),
        "t_final": media_fase(*FASES[2]),
        "relogio_final": round(meus[-1] / base, 3),
        "adv_relogio_final": round(advs[-1] / base, 3) if advs else None,
        "apuro": min(meus) / base < LIMIAR_APURO,
    }


def _resumo_motor(com: dict | None) -> dict:
    if not com:
        return {k: None for k in ("precisao_motor", "precisao_motor_adv", "imprecisoes", "erros", "erros_graves",
                                  "adv_erros_graves", "primeiro_erro_grave", "adv_primeiro_erro_grave")}
    r = com["resumo"]
    return {
        "precisao_motor": r["precisao"], "precisao_motor_adv": r["precisao_adv"],
        "imprecisoes": r["meus"]["imprecisao"], "erros": r["meus"]["erro"], "erros_graves": r["meus"]["erro_grave"],
        "adv_erros_graves": r["adv"]["erro_grave"],
        "primeiro_erro_grave": r["primeiro_erro_grave"], "adv_primeiro_erro_grave": r["adv_primeiro_erro_grave"],
    }


def linha(p: dict, mes: str, rep: dict | None, com: dict | None) -> list:
    fatos = (rep or {}).get("fatos") or {}
    reg = {
        "uuid": p["uuid"], "mes": mes,
        "url": p["url"], "fim": p["fim_utc"], "data": p["data_local"], "hora": p["hora_local"],
        "dia_semana": p["dia_semana"], "ritmo": p["ritmo"], "controle": p["controle"],
        "variante": p["variante"], "ranqueada": p["ranqueada"], "cor": p["cor"],
        "adversario": p["adversario"], "meu_rating": p["meu_rating"], "adv_rating": p["adv_rating"],
        "resultado": p["resultado"], "motivo": p["motivo"], "eco": p["eco"],
        "abertura": p["abertura"], "familia": p["abertura_familia"], "lances": p["lances"],
        "precisao": p["precisao"], "precisao_adv": p["precisao_adv"],
        **metricas_tempo(p),
        **{k: fatos.get(k) for k in ("roque", "adv_roque", "min_saldo", "max_saldo", "saldo_final",
                                      "perdi_dama", "adv_perdeu_dama", "mate_peca", "mate_tipo", "colapso")},
        **_resumo_motor(com),
    }
    return [reg[c] for c in COLUNAS]


def jogo_visualizador(p: dict, rep: dict, com: dict | None) -> dict:
    j = {
        "fi": rep["fen_inicial"], "san": rep["san"], "uci": rep["uci"], "fen": rep["fens"],
        "clk": p.get("relogios") or [], "sal": rep["saldo"],
    }
    if com:
        j.update({"av": com["av"], "mu": com["mv"], "cl": com["classes"], "cm": com["comentarios"],
                  "mel": com["melhores"], "res": com["resumo"]})
    return j


def _gravar_se_mudou(arq, dados) -> bool:
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    if arq.exists() and arq.read_text(encoding="utf-8") == texto:
        return False
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(texto, encoding="utf-8")
    return True


def dir_publicacao(usuario: str):
    return config.DIR_DOCS_DADOS / usuario


def publicar(usuario: str, fuso_horario: str) -> bool:
    """Publica um jogador em docs/dados/<usuario>/. Retorna se algum arquivo mudou."""
    destino = dir_publicacao(usuario)
    meses = {}
    for arq in sorted(config.dir_partidas(usuario).glob("*.json")):
        meses[arq.stem] = sorted(json.loads(arq.read_text(encoding="utf-8")).get("partidas", []),
                                 key=lambda p: p["fim_utc"])
    total = sum(len(ps) for ps in meses.values())
    if not total:
        log.warning("Nenhuma partida tratada para %s; nada a publicar.", usuario)
        return False
    analises = motor.carregar_analises(usuario)

    linhas, mudou_jogos, n_analisadas, sem_tabuleiro = [], 0, 0, 0
    posicoes_treino = []
    for mes, ps in meses.items():
        jogos_mes = {}
        for p in ps:
            rep = tabuleiro.reproduzir(p)
            com = None
            an = analises.get(p["uuid"])
            if rep is None:
                sem_tabuleiro += 1
            elif an and len(an.get("av", [])) == len(rep["uci"]) + 1:
                try:
                    com = comentarios.comentar(rep["fen_inicial_completa"], rep["uci"], an,
                                               p["cor"] == "brancas", rep["chess960"])
                    com["av"], com["mv"] = an["av"], an["mv"]
                    n_analisadas += 1
                except Exception:
                    log.exception("Falha ao comentar %s", p["url"])
            linhas.append(linha(p, mes, rep, com))
            if rep is not None:
                jogos_mes[p["uuid"]] = jogo_visualizador(p, rep, com)
            if rep is not None and com is not None:
                try:
                    posicoes_treino.extend(treino.extrair(p, mes, rep, com, an))
                except Exception:
                    log.exception("Falha ao extrair posições de treino de %s", p["url"])
        mudou_jogos += _gravar_se_mudou(destino / "jogos" / f"{mes}.json", jogos_mes)

    linhas.sort(key=lambda l: l[COLUNAS.index("fim")])
    posicoes_treino.sort(key=lambda x: (x["data"], x["ply"]), reverse=True)
    mudou_jogos += _gravar_se_mudou(destino / "treino.json", {"posicoes": posicoes_treino})
    log.info("Treino: %d posições de erro grave (%d com alternativas do motor)",
             len(posicoes_treino), sum(1 for x in posicoes_treino if len(x["aceitos"]) > 1 or analises.get(x["uuid"], {}).get("alt_v")))
    mudou_partidas = _gravar_se_mudou(destino / "partidas.json", {"colunas": COLUNAS, "linhas": linhas})

    arq_perfil = config.RAIZ / "dados" / "perfil" / f"{usuario}.json"
    perfil = json.loads(arq_perfil.read_text(encoding="utf-8")) if arq_perfil.exists() else {}
    meta = {
        "usuario": usuario,
        "fuso_horario": fuso_horario,
        "total_partidas": total,
        "analisadas_motor": n_analisadas,
        "ultima_partida": linhas[-1][COLUNAS.index("fim")],
        **perfil,
    }
    mudou_meta = _gravar_se_mudou(destino / "perfil.json", meta)
    mudou = bool(mudou_partidas or mudou_meta or mudou_jogos)
    if sem_tabuleiro:
        log.warning("%d partidas sem PGN legível (fora do visualizador)", sem_tabuleiro)
    log.info("Publicação de %s: %d partidas (%d com análise do motor) (%s)",
             usuario, total, n_analisadas, "atualizado" if mudou else "sem mudanças")
    return mudou


# Arquivos da estrutura antiga (um jogador só, direto em docs/dados/)
LEGADO = ("partidas.json", "perfil.json", "treino.json", "jogos")


def publicar_indice(usuarios: list[str], mudou: bool) -> None:
    """docs/dados/jogadores.json + gerado.json; remove pastas de quem saiu do config."""
    raiz = config.DIR_DOCS_DADOS
    jogadores = []
    for u in usuarios:
        arq = dir_publicacao(u) / "perfil.json"
        if not arq.exists():
            continue
        meta = json.loads(arq.read_text(encoding="utf-8"))
        pf, st = meta.get("perfil") or {}, meta.get("stats") or {}
        jogadores.append({
            # A URL do perfil guarda a grafia escolhida pelo jogador; `username` vem em minúsculas
            "usuario": u, "nome": (pf.get("url") or "").rstrip("/").rsplit("/", 1)[-1] or pf.get("username") or u,
            "avatar": pf.get("avatar"),
            "total_partidas": meta.get("total_partidas"), "analisadas_motor": meta.get("analisadas_motor"),
            "ultima_partida": meta.get("ultima_partida"),
            "ratings": {r: st[f"chess_{r}"]["last"]["rating"] for r in ("bullet", "blitz", "rapid", "daily")
                        if (st.get(f"chess_{r}") or {}).get("last")},
        })
    mudou |= _gravar_se_mudou(raiz / "jogadores.json", {"jogadores": jogadores})

    ativos = set(usuarios)
    for item in raiz.iterdir():
        if (item.is_dir() and item.name not in ativos) or item.name in LEGADO:
            log.info("Removendo publicação antiga: %s", item.relative_to(config.RAIZ))
            shutil.rmtree(item) if item.is_dir() else item.unlink()
            mudou = True
    # Carimbo separado: só avança quando os dados mudam, para o workflow não commitar à toa.
    if mudou or not (raiz / "gerado.json").exists():
        agora = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        _gravar_se_mudou(raiz / "gerado.json", {"gerado_em": agora})
