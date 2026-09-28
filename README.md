# Chess Tracking — histórico de partidas no Chess.com

Coleta automática do histórico de partidas de um grupo de contas do Chess.com (hoje:
**[giggsmate](https://www.chess.com/member/giggsmate)**,
**[maherculano](https://www.chess.com/member/maherculano)** e
**[PauloRicardoPalmeiras](https://www.chess.com/member/PauloRicardoPalmeiras)**) e página
estática, com seletor de jogador no topo, com:

- estatísticas — evolução do rating (geral e por ritmo), resultados por cor, abertura, horário
  e força do adversário, como as partidas terminam, sequências, atividade e gestão de tempo;
- **padrões de vitória e derrota** que se repetem (virada, vantagem desperdiçada, dama perdida,
  sem roque, tipos de mate, erros graves por fase…), cada um clicável para listar as partidas;
- **aba Partidas** (`partidas.html`): o histórico, da mais recente para a mais antiga, com busca e
  filtros, e o **visualizador lance a lance** de qualquer partida, com relógio, saldo de
  material e — quando a partida já foi analisada pelo **Stockfish** — avaliação, classificação
  de cada lance (imprecisão/erro/erro grave), melhor lance e comentário em português;
- **aba Treino** (`treino.html`): as posições logo antes de cada erro grave do jogador, para achar o
  lance certo no tabuleiro — com dica, solução, filtro por ritmo e fase, e revisão das erradas.

**Página publicada:** https://gfvdata-web.github.io/chess-tracking/

> 📄 Etapas do pipeline, formato dos dados e decisões: **[CONTEXTO.md](CONTEXTO.md)**

## Como rodar localmente

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python run_pipeline.py
```

Na primeira execução o pipeline baixa o histórico inteiro; nas seguintes, só os meses
novos e o mês corrente (coleta incremental, sem duplicar partidas).

| Comando | O que faz |
|---|---|
| `python run_pipeline.py` | Atualização incremental (o que o Action roda todo dia) |
| `python run_pipeline.py --completo` | Rebaixa e retrata todo o histórico |
| `python run_pipeline.py --sem-coleta` | Retrata a partir de `dados/brutos/`, sem chamar a API |
| `python run_pipeline.py --usuario maherculano` | Só uma conta (pode repetir `--usuario`) |
| `python run_pipeline.py --analisar` | Também analisa com Stockfish as partidas pendentes (precisa do Stockfish instalado; `STOCKFISH_PATH` se não estiver no PATH) |
| `python run_pipeline.py --analisar --orcamento-min 10 --nos 250000` | Limita o tempo de análise e define o esforço do motor (nós por posição) |
| `python -m src.analise.medir --nos d12,250000,1000000` | Compara custo × qualidade de esforços diferentes do motor (não grava nada) |
| `python run_pipeline.py -v` | Log detalhado |

Para ver a página:

```bash
python -m http.server 8742 --directory docs
```

e abrir http://localhost:8742. O jogador vai na URL (`?j=<usuario>`; sem ele, abre o
primeiro do `config.json`) e uma partida pode ser aberta direto pelo link
`…/?j=<usuario>#partida=<uuid>&lance=<n>` (o endereço acompanha a navegação no visualizador).

## Acompanhar mais uma conta

Os jogadores ficam em [`config.json`](config.json), na lista `"jogadores"`:

```json
"jogadores": [
  { "usuario": "giggsmate" },
  { "usuario": "outra_conta", "fuso_horario": "Europe/Lisbon" }
]
```

O `fuso_horario` de cada um (usado em dia da semana e horário) é opcional e cai no
`"fuso_horario"` global. Basta acrescentar a conta e rodar o pipeline: como nenhum mês dela
está no disco, a primeira coleta já baixa o histórico inteiro, e a análise pelo Stockfish
entra nas execuções seguintes. Tirar uma conta da lista remove a publicação dela
(`docs/dados/<usuario>/`) na próxima execução; os dados em `dados/` ficam.

Tudo fica separado por usuário: `dados/{brutos,partidas,analises,perfil}/<usuario>/` e
`docs/dados/<usuario>/`. `CHESS_USER=conta1,conta2` restringe uma execução a essas contas.

## Atualização automática

O workflow [`.github/workflows/atualizar-partidas.yml`](.github/workflows/atualizar-partidas.yml)
roda todo dia às 09:17 UTC (06:17 em Brasília):

1. instala as dependências e o Stockfish (`apt`), e roda `python run_pipeline.py --analisar`;
2. a análise por motor é incremental e tem orçamento de tempo (45 min por padrão), repartido
   entre os jogadores — cada um recebe o tempo restante dividido pelos que faltam, então o que
   um não usa passa para o seguinte. Analisa as partidas ainda não analisadas, das mais novas
   para as mais antigas; o que faltar fica para a execução seguinte;
3. commita `dados/` e `docs/dados/` **só se algo mudou** (sem partida nova, sem commit);
4. o GitHub Pages (branch `main`, pasta `/docs`) republica a página a cada push.

Para atualizar na hora: aba **Actions → Atualizar partidas → Run workflow** (dá para rebaixar
todo o histórico, escolher os minutos de análise e rodar só uma conta), ou pela linha de comando:

```bash
gh workflow run atualizar-partidas.yml -f orcamento=45
```

## Estrutura

| Caminho | Etapa | Papel |
|---|---|---|
| `config.json` | — | Jogadores, fuso horário e User-Agent |
| `src/coleta/chesscom.py` | 2 | Cliente da PubAPI (sequencial, User-Agent, retry em 429) → `dados/brutos/` |
| `src/tratamento/partidas.py` | 3 | Normaliza cada partida + parse do PGN → `dados/partidas/<usuario>/AAAA-MM.json` |
| `src/analise/tabuleiro.py` | 4 | Reproduz a partida (python-chess): posições, material, padrões |
| `src/analise/motor.py` | 4 | Stockfish incremental → `dados/analises/<usuario>/AAAA-MM.json` |
| `src/analise/comentarios.py` | 4 | Classificação, comentários e precisão a partir da análise |
| `src/analise/treino.py` | 4 | Critério das posições de treino (erro grave sem estar perdido) |
| `src/publicacao/painel.py` | 5 | Gera `docs/dados/<usuario>/` (tabela de partidas + lances por mês) e o índice `docs/dados/jogadores.json` |
| `src/publicacao/treino.py` | 5 | Gera `docs/dados/<usuario>/treino.json` (posições, lances legais, soluções) |
| `docs/` | 6 | Página estática: `js/jogador.js` (seletor de jogador) + `index.html` e `partidas.html` + `js/app.js` (estatísticas e lista, mesmos filtros) + `js/visualizador.js` (partida lance a lance); `treino.html` + `js/treino.js` |

## Licença dos dados

Dados públicos da [API pública do Chess.com](https://www.chess.com/news/view/published-data-api).
Tabuleiro: [chessground](https://github.com/lichess-org/chessground) (GPL-3.0), carregado do
jsDelivr. Análise: [Stockfish](https://stockfishchess.org/) (GPL-3.0), rodando no GitHub Actions.
