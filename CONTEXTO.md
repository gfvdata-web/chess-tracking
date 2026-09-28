# CONTEXTO — Chess Tracking

Etapas, contrato de dados e convenções deste repositório. Segue a anatomia dos repositórios
`fonte-*` e do `painel-status` da conta gfvdata-web (ver `controle-global/GUIA-REPOSITORIOS.md`).

## Fonte

API pública do Chess.com (PubAPI), sem autenticação:

| Endpoint | Uso |
|---|---|
| `/pub/player/{user}` | perfil (avatar, país, data de cadastro) |
| `/pub/player/{user}/stats` | rating atual, recorde e V/E/D por ritmo |
| `/pub/player/{user}/games/archives` | lista de meses com partidas |
| `/pub/player/{user}/games/{AAAA}/{MM}` | partidas do mês (JSON com PGN) |

Regras respeitadas: User-Agent identificando o projeto (`config.json`), requisições em
sequência com 0,5 s entre elas, e retry com espera crescente em 429/5xx (respeitando
`Retry-After`). 404/410 são registrados e ignorados.

## Etapas

| Etapa | Módulo | Entrada → Saída |
|---|---|---|
| 2 Coleta | `src/coleta/chesscom.py` | API → `dados/brutos/<usuario>/AAAA-MM.json` (não versionado) e `dados/perfil/<usuario>.json` |
| 3 Tratamento | `src/tratamento/partidas.py` | brutos → `dados/partidas/<usuario>/AAAA-MM.json` (versionado) |
| 5 Publicação | `src/publicacao/painel.py` | partidas tratadas → `docs/dados/*.json` |
| 6 Página | `docs/` | lê `docs/dados/` e agrega no navegador |

### Coleta incremental

- Cada mês tratado guarda `"completo": true|false`. Um mês é marcado completo quando foi
  baixado depois do fim do mês (+1 dia de folga) — o arquivo do Chess.com não muda mais.
- A execução normal baixa a lista de meses e só busca os que não estão completos no disco
  (na prática, o mês corrente e meses novos).
- Ao gravar um mês, as partidas são mescladas pela chave `uuid` (ou `url`, se faltar): nada
  duplica, e partidas reprocessadas substituem a versão anterior.

### Por que JSON versionado (e não SQLite)

1. Meses passados são imutáveis → cada commit diário só altera o arquivo do mês corrente;
   o diff é pequeno e legível. Um `.db` binário seria reescrito inteiro a cada commit.
2. O repositório é o próprio estado da coleta incremental — o Action não precisa de cache.
3. Zero dependência extra; a página estática lê JSON diretamente.

## Contrato: `dados/partidas/<usuario>/AAAA-MM.json`

```jsonc
{ "usuario": "giggsmate", "mes": "2026-09", "completo": false, "partidas": [ {
  "uuid": "…", "url": "https://www.chess.com/game/live/…",
  "fim_utc": "2026-09-27T19:59:42Z", "inicio_utc": "…",
  "data_local": "2026-09-27", "hora_local": 16, "dia_semana": 6,   // 0 = segunda; fuso de config.json
  "ritmo": "rapid", "controle": "600+5", "variante": "chess", "ranqueada": true,
  "cor": "brancas", "adversario": "…", "meu_rating": 485, "adv_rating": 398,
  "resultado": "vitoria|derrota|empate", "motivo": "mate|abandono|tempo|saiu_da_partida|acordo|repeticao|afogamento|material_insuficiente|regra_50_lances|tempo_vs_material|outro",
  "codigo_resultado": { "meu": "win", "adversario": "resigned" },   // códigos crus do Chess.com
  "eco": "C20", "abertura": "King's Pawn Opening Leonardis Variation", "abertura_familia": "King's Pawn Opening",
  "abertura_url": "https://www.chess.com/openings/…",
  "lances": 26, "meios_lances": 51,
  "precisao": null, "precisao_adv": null,        // só em partidas analisadas no Chess.com
  "relogios": [603.3, 598.8, …],                 // segundos restantes após cada meio-lance
  "pgn": "…"
} ] }
```

- **Motivo** é sempre do ponto de vista de quem perdeu: numa vitória, é o código do adversário
  (`resigned` → `abandono`); numa derrota, o meu.
- **Abertura**: a API não traz o nome, só o `ECOUrl`. O nome sai do slug, sem a sequência de
  lances; a família corta no primeiro "Opening/Defense/Game/Gambit/Attack/System"
  (`Alapin Sicilian Defense` → `Sicilian Defense`). Apóstrofos perdidos no slug são repostos
  por uma tabela (`GRAFIA`).
- **Relógio**: daily não tem `[%clk]` útil; as métricas de tempo ficam `null` nessas partidas.

## Publicação: `docs/dados/`

| Arquivo | Conteúdo |
|---|---|
| `partidas.json` | tabela colunar `{colunas, linhas}` sem PGN, uma linha por partida, com métricas de tempo |
| `perfil.json` | perfil, stats por ritmo, usuário e fuso |
| `gerado.json` | carimbo da última geração **com mudança** (evita commit diário vazio) |

Métricas de tempo (por partida ao vivo): segundos gastos em média por lance meu em cada fase
(lances 1–10, 11–25, 26+; gasto = relógio anterior − atual + incremento), fração do tempo-base
restante no fim (meu e do adversário) e `apuro` = ficou com < 10% do tempo-base.

## Página

`docs/index.html` + `js/app.js` + `css/estilo.css`, Chart.js 4.4.3 via jsDelivr, GoatCounter.
Filtros (ritmo e período) valem para a página inteira; toda agregação é feita no navegador.
Cores de série validadas para daltonismo e contraste nos modos claro e escuro; todo gráfico
tem um "Ver dados" com a tabela equivalente.
