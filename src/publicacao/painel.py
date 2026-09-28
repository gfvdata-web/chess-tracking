"""Etapa 5 — publicação: partidas tratadas -> JSON leve que a página lê.

Gera em docs/dados/:
- partidas.json  tabela colunar (sem PGN) com uma linha por partida, já com as
                 métricas de gestão de tempo calculadas a partir de [%clk];
- perfil.json    perfil, ratings atuais/recordes e metadados da geração.

A página faz os filtros (ritmo, período) e as agregações no navegador; com
~1k partidas o arquivo fica na casa das centenas de KB.
"""
import json
import logging
from datetime import datetime, timezone
from statistics import mean

from src import config
from src.tratamento.partidas import carregar_todas

log = logging.getLogger("publicacao")

COLUNAS = [
    "url", "fim", "data", "hora", "dia_semana", "ritmo", "controle", "variante", "ranqueada",
    "cor", "adversario", "meu_rating", "adv_rating", "resultado", "motivo", "eco", "abertura",
    "familia", "lances", "precisao", "precisao_adv",
    # gestão de tempo (null em daily ou sem relógio)
    "t_abertura", "t_meio", "t_final", "relogio_final", "adv_relogio_final", "apuro",
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


def linha(p: dict) -> list:
    reg = {
        "url": p["url"], "fim": p["fim_utc"], "data": p["data_local"], "hora": p["hora_local"],
        "dia_semana": p["dia_semana"], "ritmo": p["ritmo"], "controle": p["controle"],
        "variante": p["variante"], "ranqueada": p["ranqueada"], "cor": p["cor"],
        "adversario": p["adversario"], "meu_rating": p["meu_rating"], "adv_rating": p["adv_rating"],
        "resultado": p["resultado"], "motivo": p["motivo"], "eco": p["eco"],
        "abertura": p["abertura"], "familia": p["abertura_familia"], "lances": p["lances"],
        "precisao": p["precisao"], "precisao_adv": p["precisao_adv"],
        **metricas_tempo(p),
    }
    return [reg[c] for c in COLUNAS]


def _gravar_se_mudou(arq, dados) -> bool:
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    if arq.exists() and arq.read_text(encoding="utf-8") == texto:
        return False
    arq.write_text(texto, encoding="utf-8")
    return True


def publicar(usuario: str, cfg: dict) -> None:
    partidas = sorted(carregar_todas(usuario), key=lambda p: p["fim_utc"])
    if not partidas:
        log.warning("Nenhuma partida tratada para %s; nada a publicar.", usuario)
        return
    config.DIR_DOCS_DADOS.mkdir(parents=True, exist_ok=True)

    tabela = {"colunas": COLUNAS, "linhas": [linha(p) for p in partidas]}
    mudou_partidas = _gravar_se_mudou(config.DIR_DOCS_DADOS / "partidas.json", tabela)

    arq_perfil = config.RAIZ / "dados" / "perfil" / f"{usuario}.json"
    perfil = json.loads(arq_perfil.read_text(encoding="utf-8")) if arq_perfil.exists() else {}
    meta = {
        "usuario": usuario,
        "fuso_horario": cfg["fuso_horario"],
        "total_partidas": len(partidas),
        "ultima_partida": partidas[-1]["fim_utc"],
        **perfil,
    }
    mudou_meta = _gravar_se_mudou(config.DIR_DOCS_DADOS / "perfil.json", meta)
    # Carimbo de geração separado: só avança quando os dados de fato mudam,
    # para o workflow não commitar todo dia sem partida nova.
    if mudou_partidas or mudou_meta or not (config.DIR_DOCS_DADOS / "gerado.json").exists():
        agora = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        _gravar_se_mudou(config.DIR_DOCS_DADOS / "gerado.json", {"gerado_em": agora})
    log.info("Publicação: %d partidas em docs/dados/ (%s)", len(partidas),
             "atualizado" if (mudou_partidas or mudou_meta) else "sem mudanças")
