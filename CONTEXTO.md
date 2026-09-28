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
| 4 Tabuleiro | `src/analise/tabuleiro.py` | PGN → lances, posições, saldo de material e fatos para os padrões (sem motor) |
| 4 Motor | `src/analise/motor.py` | PGN → `dados/analises/<usuario>/AAAA-MM.json` (versionado; Stockfish, opcional) |
| 4 Comentários | `src/analise/comentarios.py` | análise → classificação, comentário e precisão por lance (na publicação) |
| 5 Publicação | `src/publicacao/painel.py` | partidas tratadas → `docs/dados/<usuario>/*.json` + `docs/dados/jogadores.json` |
| 6 Página | `docs/` | lê `docs/dados/` do jogador escolhido e agrega no navegador |

### Vários jogadores

- `config.json` → `"jogadores": [{"usuario", "fuso_horario"?}]` (fuso omitido = o global).
  O formato antigo (`"usuario": "…"`) ainda é aceito.
- `run_pipeline.py` roda coleta e tratamento para cada um; um erro de API num jogador vai
  para o log e não impede os demais. `--usuario X` (ou `CHESS_USER=a,b`) restringe a execução.
- Orçamento do Stockfish repartido: cada jogador recebe `tempo restante ÷ jogadores que
  faltam`, então o que um não usa (histórico já analisado) passa para o seguinte.
- Conta nova: nenhum mês dela está marcado como completo no disco, então a coleta incremental
  já baixa o histórico inteiro, sem `--completo`.
- Partidas entre dois jogadores acompanhados aparecem nos dois, cada uma do ponto de vista
  do dono da página.

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

## Análise (Etapa 4)

### Tabuleiro — `tabuleiro.py` (python-chess, sem motor)

Reproduz cada partida e calcula, do meu ponto de vista (peão 1, cavalo/bispo 3, torre 5, dama 9):

| Fato | Definição |
|---|---|
| `min_saldo` / `max_saldo` | pior/melhor saldo de material **que se sustentou por 3 meios-lances** (ignora trocas em andamento) |
| `saldo_final` | saldo na posição final |
| `perdi_dama` / `adv_perdeu_dama` | lance em que a dama caiu sem a dama adversária cair nos 2 meios-lances seguintes |
| `roque` / `adv_roque` | `curto`, `longo` ou vazio |
| `mate_peca` | peça que fez o lance do mate |
| `mate_tipo` | `pastor` (dama em f7/f2 em ≤ 8 lances), `afogado` (cavalo, rei cercado pelas próprias peças), `corredor` (torre/dama na última fileira do rei), `rapido` (≤ 15 lances), `outro` |
| `colapso` | lance a partir do qual fiquei com ≥ 3 a menos e não recuperei mais |

A página combina esses fatos nos **padrões de vitória e derrota** (`PADROES` em `docs/js/app.js`).

### Motor — `motor.py` (Stockfish)

- Stockfish oficial, versão e SHA-256 fixados no workflow (hoje **Stockfish 19**); trocar a
  versão é editar `SF_TAG`/`SF_SHA256` em `atualizar-partidas.yml`.
- Avalia a posição inicial e a posição após cada meio-lance com limite de **nós** por posição
  (`NOS_PADRAO`), não de profundidade: custo previsível e o mesmo critério da análise do Lichess.
  A análise grava `nos` e `motor` (nome e versão).
- Guarda por partida: `av` (avaliação em centipeões do ponto de vista das brancas; mate =
  ±(10000 − distância)), `mv` (melhor lance UCI), `pv` (4 meios-lances da linha principal).
- Incremental: só analisa partidas sem análise da `VERSAO` atual ou com menos nós (análises antigas,
  por profundidade, são refeitas). Se o motor encerrar (o SF 19 sai diante de posição inválida), é reaberto.
  Ordem: mais novas primeiro; para no orçamento de tempo e grava a cada 25 partidas.
- No GitHub Actions (4 vCPU), antes: Stockfish 16 a profundidade 12, ~38 partidas por minuto.
- `python -m src.analise.medir --nos d12,250000,1000000` (ou o input `medir` do workflow) compara
  custo × qualidade de esforços diferentes nas mesmas partidas, sem gravar nada.

### Comentários — `comentarios.py`

- Chance de vitória (fórmula do Lichess): `50 + 50·(2/(1+e^(−0,00368·cp)) − 1)`.
- Classificação pela queda na chance de quem jogou: imprecisão ≥ 5 p.p., erro ≥ 10, erro
  grave ≥ 15; perder um mate forçado conta no mínimo como imprecisão.
- Motivo do erro (quando identificável): permite mate, perdeu mate, perde material na linha
  do motor, ou deixou de capturar peça. Sempre: melhor lance e avaliação para quem jogou.
- Precisão por jogador pelo método do Lichess (média ponderada pela volatilidade + média
  harmônica). Fica em geral alguns pontos acima da precisão do Chess.com.

### Treino — `treino.py` (análise) e `publicacao/treino.py`

- Posição de treino = a posição antes de um lance meu em que a minha chance de vitória caiu
  ≥ 15 p.p. (erro grave), desde que eu tivesse ≥ 10% de chance antes (errar numa posição já
  perdida não ensina nada). Só xadrez padrão.
- O motor calcula, depois da análise principal e dentro do mesmo orçamento, as 3 melhores
  jogadas dessas posições (`multipv 3`, mesmo limite de nós) e grava em `alt` da análise da partida.
- Lances aceitos no treino: o melhor lance da análise principal + alternativas do multipv que
  perdem no máximo 5 p.p. de chance em relação à melhor. Sem `alt` ainda, só o melhor lance vale.
- Página: `treino.html` + `js/treino.js`. O tabuleiro só permite lances legais (lista gerada
  pelo python-chess), 3 tentativas, dica (peça a mexer), solução com a linha do motor e o que
  foi jogado na partida. Progresso no `localStorage` (chave `treino-progresso-v1:<usuario>`;
  a chave antiga, sem usuário, é migrada para giggsmate na primeira visita); acerto só
  conta de primeira e sem dica — o resto volta em "Revisar erradas". Link direto:
  `treino.html#<uuid>:<ply>`.

## Publicação: `docs/dados/`

Na raiz, `jogadores.json` (índice para o seletor: usuário, nome com a grafia da URL do perfil,
avatar, total de partidas, analisadas, última partida e rating atual por ritmo) e `gerado.json`.
O resto fica em `docs/dados/<usuario>/`. Pastas de contas que saíram do `config.json` são
removidas na publicação.

| Arquivo | Conteúdo |
|---|---|
| `partidas.json` | tabela colunar `{colunas, linhas}` sem PGN, uma linha por partida: dados da partida, métricas de tempo, fatos de tabuleiro e resumo do motor |
| `jogos/AAAA-MM.json` | por partida (`uuid`): `fi` posição inicial, `san`/`uci`/`fen` por meio-lance, `clk` relógio, `sal` saldo de material; se analisada, `av`, `mu` (melhor lance), `cl` (classe), `cm` (comentário), `mel` (melhor em SAN), `res` (resumo). Carregado sob demanda pelo visualizador |
| `treino.json` | posições de treino: FEN, lances legais (`dests`), lance jogado, melhor, aceitos, linha do motor, chance antes/depois e contexto da partida |
| `perfil.json` | perfil, stats por ritmo, usuário e fuso |
| `gerado.json` (raiz) | carimbo da última geração **com mudança** em qualquer jogador (evita commit diário vazio) |

Métricas de tempo (por partida ao vivo): segundos gastos em média por lance meu em cada fase
(lances 1–10, 11–25, 26+; gasto = relógio anterior − atual + incremento), fração do tempo-base
restante no fim (meu e do adversário) e `apuro` = ficou com < 10% do tempo-base.

## Página

`docs/index.html` + `js/app.js` (estatísticas, padrões, explorador) + `js/visualizador.js`
(partida lance a lance, com o tabuleiro [chessground](https://github.com/lichess-org/chessground)
10.4.0 via jsDelivr) + `css/estilo.css`, Chart.js 4.4.3 via jsDelivr, GoatCounter.
Jogador na URL: `?j=<usuario>` (sem ele, ou com uma conta que não existe, abre o primeiro do
`jogadores.json`); `js/jogador.js` monta o seletor e mantém o `?j=` nas abas.
Link direto para uma partida: `?j=<usuario>#partida=<uuid>&lance=<n>`.
Filtros (ritmo e período) valem para a página inteira; toda agregação é feita no navegador.
Cores de série validadas para daltonismo e contraste nos modos claro e escuro; todo gráfico
tem um "Ver dados" com a tabela equivalente.
