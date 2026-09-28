# Chess Tracking — histórico de partidas no Chess.com

Coleta automática do histórico de partidas de uma conta do Chess.com (hoje:
**[giggsmate](https://www.chess.com/member/giggsmate)**) e página estática com estatísticas:
evolução do rating, resultados por cor, ritmo, abertura, horário e força do adversário,
como as partidas terminam, sequências, atividade e gestão de tempo.

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
| `python run_pipeline.py -v` | Log detalhado |

Para ver a página:

```bash
python -m http.server 8742 --directory docs
```

e abrir http://localhost:8742.

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

1. instala as dependências e roda `python run_pipeline.py`;
2. commita `dados/` e `docs/dados/` **só se algo mudou** (sem partida nova, sem commit);
3. o GitHub Pages (branch `main`, pasta `/docs`) republica a página a cada push.

Para atualizar na hora: aba **Actions → Atualizar partidas → Run workflow** (há a opção de
rebaixar todo o histórico), ou pela linha de comando:

```bash
gh workflow run atualizar-partidas.yml
```

## Estrutura

| Caminho | Etapa | Papel |
|---|---|---|
| `config.json` | — | Usuário, fuso horário e User-Agent |
| `src/coleta/chesscom.py` | 2 | Cliente da PubAPI (sequencial, User-Agent, retry em 429) → `dados/brutos/` |
| `src/tratamento/partidas.py` | 3 | Normaliza cada partida + parse do PGN → `dados/partidas/<usuario>/AAAA-MM.json` |
| `src/publicacao/painel.py` | 5 | Agrega para a página → `docs/dados/` |
| `docs/` | 6 | Página estática publicada no GitHub Pages |

## Licença dos dados

Dados públicos da [API pública do Chess.com](https://www.chess.com/news/view/published-data-api).
