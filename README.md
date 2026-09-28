# Chess Tracking — histórico de partidas no Chess.com

Coleta automática do histórico de partidas de uma conta do Chess.com (hoje:
**[giggsmate](https://www.chess.com/member/giggsmate)**) e página estática com:

- estatísticas — evolução do rating (geral e por ritmo), resultados por cor, abertura, horário
  e força do adversário, como as partidas terminam, sequências, atividade e gestão de tempo;
- **padrões de vitória e derrota** que se repetem (virada, vantagem desperdiçada, dama perdida,
  sem roque, tipos de mate, erros graves por fase…), cada um clicável para listar as partidas;
- **visualizador lance a lance** de qualquer partida do histórico, com relógio, saldo de
  material e — quando a partida já foi analisada pelo **Stockfish** — avaliação, classificação
  de cada lance (imprecisão/erro/erro grave), melhor lance e comentário em português.

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
| `python run_pipeline.py --analisar` | Também analisa com Stockfish as partidas pendentes (precisa do Stockfish instalado; `STOCKFISH_PATH` se não estiver no PATH) |
| `python run_pipeline.py --analisar --orcamento-min 10 --profundidade 12` | Limita o tempo de análise e define a profundidade |
| `python run_pipeline.py -v` | Log detalhado |

Para ver a página:

```bash
python -m http.server 8742 --directory docs
```

e abrir http://localhost:8742. Uma partida pode ser aberta direto pelo link
`…/#partida=<uuid>&lance=<n>` (o endereço acompanha a navegação no visualizador).

## Trocar ou acompanhar outra conta

O usuário fica em [`config.json`](config.json) (`"usuario"`), junto com o fuso horário usado
para dia da semana e horário (`"fuso_horario"`) e o User-Agent enviado à API. Para rodar
pontualmente para outra conta sem editar o arquivo:

```bash
CHESS_USER=outra_conta python run_pipeline.py        # PowerShell: $env:CHESS_USER="outra_conta"
```

As partidas tratadas ficam separadas por usuário em `dados/partidas/<usuario>/`. A página
publica a conta que o pipeline rodou por último.

## Atualização automática

O workflow [`.github/workflows/atualizar-partidas.yml`](.github/workflows/atualizar-partidas.yml)
roda todo dia às 09:17 UTC (06:17 em Brasília):

1. instala as dependências e o Stockfish (`apt`), e roda `python run_pipeline.py --analisar`;
2. a análise por motor é incremental e tem orçamento de tempo (45 min por padrão): analisa as
   partidas ainda não analisadas, das mais novas para as mais antigas — o que faltar fica
   para a execução seguinte;
3. commita `dados/` e `docs/dados/` **só se algo mudou** (sem partida nova, sem commit);
4. o GitHub Pages (branch `main`, pasta `/docs`) republica a página a cada push.

Para atualizar na hora: aba **Actions → Atualizar partidas → Run workflow** (dá para rebaixar
todo o histórico e escolher os minutos de análise), ou pela linha de comando:

```bash
gh workflow run atualizar-partidas.yml -f orcamento=45
```

## Estrutura

| Caminho | Etapa | Papel |
|---|---|---|
| `config.json` | — | Usuário, fuso horário e User-Agent |
| `src/coleta/chesscom.py` | 2 | Cliente da PubAPI (sequencial, User-Agent, retry em 429) → `dados/brutos/` |
| `src/tratamento/partidas.py` | 3 | Normaliza cada partida + parse do PGN → `dados/partidas/<usuario>/AAAA-MM.json` |
| `src/analise/tabuleiro.py` | 4 | Reproduz a partida (python-chess): posições, material, padrões |
| `src/analise/motor.py` | 4 | Stockfish incremental → `dados/analises/<usuario>/AAAA-MM.json` |
| `src/analise/comentarios.py` | 4 | Classificação, comentários e precisão a partir da análise |
| `src/publicacao/painel.py` | 5 | Gera `docs/dados/` (tabela de partidas + lances por mês) |
| `docs/` | 6 | Página estática (`js/app.js` estatísticas, `js/visualizador.js` tabuleiro) |

## Licença dos dados

Dados públicos da [API pública do Chess.com](https://www.chess.com/news/view/published-data-api).
Tabuleiro: [chessground](https://github.com/lichess-org/chessground) (GPL-3.0), carregado do
jsDelivr. Análise: [Stockfish](https://stockfishchess.org/) (GPL-3.0), rodando no GitHub Actions.
