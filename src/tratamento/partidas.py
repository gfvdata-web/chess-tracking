"""Etapa 3 — tratamento: partida crua da API -> registro normalizado.

Cada mês vira dados/partidas/<usuario>/AAAA-MM.json. A chave de cada partida
é o `uuid` (ou a `url`, se o uuid faltar); ao reprocessar um mês, partidas já
existentes são substituídas, nunca duplicadas.
"""
import json
import logging
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src import config

log = logging.getLogger("tratamento")

# Códigos de resultado do Chess.com -> (resultado, motivo)
EMPATES = {
    "agreed": "acordo",
    "repetition": "repeticao",
    "stalemate": "afogamento",
    "insufficient": "material_insuficiente",
    "50move": "regra_50_lances",
    "timevsinsufficient": "tempo_vs_material",
}
DERROTAS = {
    "checkmated": "mate",
    "resigned": "abandono",
    "timeout": "tempo",
    "abandoned": "saiu_da_partida",
    "lose": "outro",
    "kingofthehill": "outro",
    "threecheck": "outro",
    "bughousepartnerlose": "outro",
}

RE_TAG = re.compile(r'^\[(\w+) "(.*)"\]\s*$', re.M)
RE_CLK = re.compile(r"\[%clk (\d+):(\d+):(\d+(?:\.\d+)?)\]")
RE_COMENTARIO = re.compile(r"\{[^}]*\}")
RE_NUM_LANCE = re.compile(r"\d+\.(\.\.)?")
RESULTADOS_PGN = {"1-0", "0-1", "1/2-1/2", "*"}

# Palavras que fecham o nome-base de uma abertura ("Sicilian Defense", "Kings Pawn Opening")
FECHA_FAMILIA = {"Opening", "Defense", "Game", "Gambit", "Attack", "System", "Countergambit"}
COMPLEMENTO_FAMILIA = {"Declined", "Accepted"}


def parse_pgn(pgn: str) -> tuple[dict, list[str], list[float]]:
    """Retorna (tags, lances SAN, relógio em segundos após cada meio-lance)."""
    tags = dict(RE_TAG.findall(pgn))
    corpo = RE_TAG.sub("", pgn)
    relogios = [round(int(h) * 3600 + int(m) * 60 + float(s), 1) for h, m, s in RE_CLK.findall(corpo)]
    sem_coment = RE_COMENTARIO.sub(" ", corpo)
    sem_num = RE_NUM_LANCE.sub(" ", sem_coment)
    lances = [t for t in sem_num.split() if t not in RESULTADOS_PGN and not t.startswith("$")]
    return tags, lances, relogios


# O slug do Chess.com perde apóstrofos e hífens dos nomes próprios
GRAFIA = {
    "Kings": "King's", "Queens": "Queen's", "Alekhines": "Alekhine's", "Petrovs": "Petrov's",
    "Owens": "Owen's", "Bishops": "Bishop's", "Birds": "Bird's", "Larsens": "Larsen's",
    "Philidors": "Philidor's", "Carls": "Carl's", "Caro Kann": "Caro-Kann",
    "Van t Kruijs": "Van't Kruijs", "Nimzo Larsen": "Nimzo-Larsen",
}
# Prefixos que separariam a mesma família ("Alapin Sicilian Defense" -> "Sicilian Defense")
PREFIXOS_FAMILIA = {"Alapin", "Closed", "Open", "Old", "Modern", "Accelerated"}


def _grafia(texto: str) -> str:
    for errado, certo in GRAFIA.items():
        texto = re.sub(rf"\b{errado}\b", certo, texto)
    return texto


def nome_abertura(eco_url: str | None) -> tuple[str | None, str | None]:
    """'…/openings/Kings-Pawn-Opening-Leonardis-Variation' -> (nome sem lances, família).

    Ex.: 'Indian-Game...3.Bd3-Bg7' -> ('Indian Game', 'Indian Game').
    """
    if not eco_url or "/openings/" not in eco_url:
        return None, None
    slug = eco_url.rsplit("/openings/", 1)[1].strip("/")
    if slug.lower() == "undefined":
        return "Não identificada", "Não identificada"
    # Corta a sequência de lances que às vezes vem colada ao nome ("Game...3.Bd3", "Defense-2.d4")
    slug = re.split(r"\.\.\.|-(?=\d)", slug, maxsplit=1)[0]
    partes = [p for p in slug.split("-") if p]
    nome = " ".join(partes)
    familia = None
    for i, p in enumerate(partes[:6]):
        if p in FECHA_FAMILIA:
            fim = i + 1
            if fim < len(partes) and partes[fim] in COMPLEMENTO_FAMILIA:
                fim += 1
            ini = 1 if partes[0] in PREFIXOS_FAMILIA and i > 1 else 0
            familia = " ".join(partes[ini:fim])
            break
    if familia is None:
        familia = " ".join(partes[:3]) or nome
    return _grafia(nome), _grafia(familia)


def tratar_partida(g: dict, usuario: str, fuso: ZoneInfo) -> dict | None:
    brancas, pretas = g.get("white", {}), g.get("black", {})
    if brancas.get("username", "").lower() == usuario:
        cor, eu, adv = "brancas", brancas, pretas
    elif pretas.get("username", "").lower() == usuario:
        cor, eu, adv = "pretas", pretas, brancas
    else:
        log.warning("Partida %s não tem %s como jogador; ignorada", g.get("url"), usuario)
        return None

    meu_cod, adv_cod = eu.get("result", ""), adv.get("result", "")
    if meu_cod == "win":
        resultado, motivo = "vitoria", DERROTAS.get(adv_cod, "outro")
    elif meu_cod in EMPATES:
        resultado, motivo = "empate", EMPATES[meu_cod]
    else:
        resultado, motivo = "derrota", DERROTAS.get(meu_cod, "outro")

    pgn = g.get("pgn", "") or ""
    tags, lances, relogios = parse_pgn(pgn)
    abertura, familia = nome_abertura(tags.get("ECOUrl") or g.get("eco"))

    fim = datetime.fromtimestamp(g["end_time"], tz=timezone.utc)
    inicio = None
    if g.get("start_time"):
        inicio = datetime.fromtimestamp(g["start_time"], tz=timezone.utc)
    elif tags.get("UTCDate") and tags.get("UTCTime"):
        try:
            inicio = datetime.strptime(f'{tags["UTCDate"]} {tags["UTCTime"]}', "%Y.%m.%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    fim_local = fim.astimezone(fuso)

    acc = g.get("accuracies") or {}
    lado, lado_adv = ("white", "black") if cor == "brancas" else ("black", "white")

    return {
        "uuid": g.get("uuid") or g.get("url"),
        "url": g.get("url"),
        "fim_utc": fim.isoformat().replace("+00:00", "Z"),
        "inicio_utc": inicio.isoformat().replace("+00:00", "Z") if inicio else None,
        "data_local": fim_local.strftime("%Y-%m-%d"),
        "hora_local": fim_local.hour,
        "dia_semana": fim_local.weekday(),  # 0 = segunda
        "ritmo": g.get("time_class"),
        "controle": g.get("time_control"),
        "variante": g.get("rules", "chess"),
        "ranqueada": bool(g.get("rated")),
        "cor": cor,
        "adversario": adv.get("username"),
        "meu_rating": eu.get("rating"),
        "adv_rating": adv.get("rating"),
        "resultado": resultado,
        "motivo": motivo,
        "codigo_resultado": {"meu": meu_cod, "adversario": adv_cod},
        "eco": tags.get("ECO"),
        "abertura": abertura,
        "abertura_url": tags.get("ECOUrl") or g.get("eco"),
        "abertura_familia": familia,
        "lances": (len(lances) + 1) // 2,
        "meios_lances": len(lances),
        "precisao": acc.get(lado),
        "precisao_adv": acc.get(lado_adv),
        "relogios": relogios,  # segundos restantes após cada meio-lance (brancas, pretas, ...)
        "pgn": pgn,
    }


def gravar_mes(usuario: str, mes: str, games: list[dict], completo: bool, fuso: ZoneInfo) -> tuple[int, int]:
    """Mescla as partidas do mês no arquivo tratado. Retorna (total, novas)."""
    destino = config.dir_partidas(usuario)
    destino.mkdir(parents=True, exist_ok=True)
    arq = destino / f"{mes}.json"

    existentes = {}
    if arq.exists():
        antigo = json.loads(arq.read_text(encoding="utf-8"))
        existentes = {p["uuid"]: p for p in antigo.get("partidas", [])}
    n_antes = len(existentes)

    for g in games:
        try:
            p = tratar_partida(g, usuario, fuso)
        except Exception:  # uma partida malformada não derruba o mês
            log.exception("Falha ao tratar %s", g.get("url"))
            continue
        if p:
            existentes[p["uuid"]] = p

    partidas = sorted(existentes.values(), key=lambda p: (p["fim_utc"], p["uuid"]))
    conteudo = {"usuario": usuario, "mes": mes, "completo": completo, "partidas": partidas}
    novo_texto = json.dumps(conteudo, ensure_ascii=False, indent=1)
    if not arq.exists() or arq.read_text(encoding="utf-8") != novo_texto:
        arq.write_text(novo_texto, encoding="utf-8")
    return len(partidas), len(partidas) - n_antes


def tratar(usuario: str, fuso_nome: str, baixados: list[dict]) -> int:
    fuso = ZoneInfo(fuso_nome)
    novas_total = 0
    for item in baixados:
        total, novas = gravar_mes(usuario, item["mes"], item["games"], item["completo"], fuso)
        novas_total += novas
        if novas:
            log.info("%s: %d partidas (+%d novas)", item["mes"], total, novas)
    log.info("Tratamento concluído: %d partidas novas", novas_total)
    return novas_total


def carregar_brutos(usuario: str) -> list[dict]:
    """Relê os brutos já baixados (para --sem-coleta)."""
    itens = []
    for arq in sorted(config.dir_brutos(usuario).glob("*.json")):
        mes = arq.stem
        dados = json.loads(arq.read_text(encoding="utf-8"))
        ja_completo = False
        tratado = config.dir_partidas(usuario) / f"{mes}.json"
        if tratado.exists():
            ja_completo = json.loads(tratado.read_text(encoding="utf-8")).get("completo", False)
        itens.append({"mes": mes, "completo": ja_completo, "games": dados.get("games", [])})
    return itens


def carregar_todas(usuario: str) -> list[dict]:
    partidas = []
    for arq in sorted(config.dir_partidas(usuario).glob("*.json")):
        partidas.extend(json.loads(arq.read_text(encoding="utf-8")).get("partidas", []))
    return partidas
