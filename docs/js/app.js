/* ===== Chess Tracking — painel =====
   Lê docs/dados/{partidas,perfil,gerado}.json (gerados por run_pipeline.py),
   aplica os filtros de ritmo e período e agrega tudo no navegador. */
(function () {
  "use strict";

  // ---------- Constantes ----------
  const RITMOS = ["bullet", "blitz", "rapid", "daily"];           // ordem fixa (cor segue o ritmo)
  const NOME_RITMO = { bullet: "Bullet", blitz: "Blitz", rapid: "Rapid", daily: "Daily" };
  const RESULTADOS = [
    { chave: "vitoria", nome: "Vitórias", cor: "--vitoria" },
    { chave: "empate", nome: "Empates", cor: "--empate" },
    { chave: "derrota", nome: "Derrotas", cor: "--derrota" },
  ];
  const MOTIVOS = {
    mate: "Xeque-mate", abandono: "Abandono", tempo: "Tempo", saiu_da_partida: "Saiu da partida",
    acordo: "Acordo", repeticao: "Repetição", afogamento: "Afogamento",
    material_insuficiente: "Material insuficiente", regra_50_lances: "Regra dos 50 lances",
    tempo_vs_material: "Tempo vs. material insuficiente", outro: "Outro",
  };
  const DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
  const DIAS_LONGOS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"];
  const PERIODOS = [
    { chave: "tudo", nome: "Tudo" },
    { chave: "ano", nome: "Este ano" },
    { chave: "12m", nome: "12 meses" },
    { chave: "90d", nome: "90 dias" },
    { chave: "30d", nome: "30 dias" },
  ];
  const FAIXAS_FORCA = [
    { ate: -200, nome: "< −200" },
    { ate: -100, nome: "−200 a −101" },
    { ate: -50, nome: "−100 a −51" },
    { ate: 0, nome: "−50 a −1" },
    { ate: 50, nome: "0 a +49" },
    { ate: 100, nome: "+50 a +99" },
    { ate: 200, nome: "+100 a +199" },
    { ate: Infinity, nome: "+200 ou mais" },
  ];
  const FASES = [
    { chave: "t_abertura", nome: "Abertura (lances 1–10)" },
    { chave: "t_meio", nome: "Meio-jogo (11–25)" },
    { chave: "t_final", nome: "Final (26+)" },
  ];
  const INTERVALO_SESSAO_MS = 60 * 60 * 1000;   // partida "seguinte" = até 1h depois
  const PAUSA_LONGA_MS = 60 * 24 * 3600 * 1000; // >60 dias sem jogar o ritmo quebra a linha do rating

  // ---------- Estado ----------
  const estado = {
    ritmo: "todos", periodo: "tudo", de: "", ate: "",
    abNivel: "familia", abCor: "todas", recentesN: 20,
  };
  let TODAS = [], PERFIL = {}, GERADO = {};
  const graficos = {};

  // ---------- Utilidades ----------
  const $ = (id) => document.getElementById(id);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const fmtInt = new Intl.NumberFormat("pt-BR");
  const pct = (x, casas = 0) => (isFinite(x) ? (x * 100).toFixed(casas).replace(".", ",") + "%" : "—");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const hojeISO = () => new Date().toLocaleDateString("sv-SE");
  const somaDias = (iso, n) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return d.toLocaleDateString("sv-SE"); };
  const fmtData = (iso) => iso.split("-").reverse().join("/");
  const fmtMes = (ms) => new Date(ms).toLocaleDateString("pt-BR", { month: "short", year: "2-digit" }).replace(". de ", "/").replace(" de ", "/");

  function contar(lista) {
    const c = { vitoria: 0, empate: 0, derrota: 0, n: lista.length };
    for (const p of lista) c[p.resultado]++;
    c.pontos = c.n ? (c.vitoria + c.empate / 2) / c.n : NaN;
    return c;
  }

  function fmtControle(ctrl) {
    if (!ctrl) return "";
    if (ctrl.includes("/")) { const s = +ctrl.split("/")[1]; return s >= 86400 ? `${s / 86400} dia${s > 86400 ? "s" : ""}/lance` : ctrl; }
    const [b, inc] = ctrl.split("+").map(Number);
    const base = b >= 60 ? `${b / 60} min` : `${b}s`;
    return inc ? `${base} + ${inc}s` : base;
  }

  function barraVED(c, grande) {
    if (!c.n) return `<div class="barra-ved${grande ? " barra-ved--grande" : ""}"></div>`;
    const seg = RESULTADOS.filter((r) => c[r.chave])
      .map((r) => `<span style="width:${(c[r.chave] / c.n) * 100}%;background:var(${r.cor})" title="${r.nome}: ${c[r.chave]} (${pct(c[r.chave] / c.n)})"></span>`)
      .join("");
    return `<div class="barra-ved${grande ? " barra-ved--grande" : ""}" role="img" aria-label="${RESULTADOS.map((r) => `${r.nome} ${pct(c[r.chave] / c.n)}`).join(", ")}">${seg}</div>`;
  }

  function legendaVED(c) {
    return `<div class="legenda">${RESULTADOS.map((r) =>
      `<span class="legenda__item"><span class="quad" style="background:var(${r.cor})"></span>${r.nome} ${c ? `<strong>${pct(c[r.chave] / c.n)}</strong> (${fmtInt.format(c[r.chave])})` : ""}</span>`).join("")}</div>`;
  }

  function tabelaDados(id, cab, linhas) {
    const el = $(id);
    const summary = el.querySelector("summary").outerHTML;
    el.innerHTML = summary + `<div class="tabela-wrap"><table><thead><tr>${cab.map((c, i) => `<th${i ? ' class="num"' : ""}>${esc(c)}</th>`).join("")}</tr></thead><tbody>${
      linhas.map((l) => `<tr>${l.map((v, i) => `<td${i ? ' class="num"' : ""}>${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  }

  // ---------- Carregamento ----------
  async function carregar() {
    const [tab, perfil, gerado] = await Promise.all(
      ["partidas", "perfil", "gerado"].map((n) => fetch(`dados/${n}.json`, { cache: "no-cache" }).then((r) => {
        if (!r.ok) throw new Error(`dados/${n}.json: HTTP ${r.status}`);
        return r.json();
      })));
    const cols = tab.colunas;
    TODAS = tab.linhas.map((l) => {
      const p = {};
      cols.forEach((c, i) => (p[c] = l[i]));
      p.ts = Date.parse(p.fim);
      return p;
    });
    PERFIL = perfil; GERADO = gerado;
  }

  // ---------- Cabeçalho ----------
  function renderCabecalho() {
    const pf = PERFIL.perfil || {};
    const nome = pf.username || PERFIL.usuario;
    const link = $("nome-usuario");
    link.textContent = nome;
    link.href = pf.url || `https://www.chess.com/member/${PERFIL.usuario}`;
    document.title = `${nome} — Chess Tracking`;
    if (pf.avatar) { const a = $("avatar"); a.src = pf.avatar; a.alt = `Avatar de ${nome}`; a.hidden = false; }
    const gerado = GERADO.gerado_em ? new Date(GERADO.gerado_em).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—";
    $("meta-gerado").textContent = `${fmtInt.format(TODAS.length)} partidas desde ${fmtData(TODAS[0].data)} · atualizado em ${gerado}`;
    $("fuso").textContent = PERFIL.fuso_horario || "UTC";

    const st = PERFIL.stats || {};
    $("ratings").innerHTML = RITMOS.map((r) => {
      const s = st[`chess_${r}`];
      if (!s || !s.last) return "";
      const rec = s.record || {};
      return `<div class="rating-card">
        <div class="rating-card__ritmo"><span class="ponto" style="background:var(--${r})"></span>${NOME_RITMO[r]}</div>
        <div class="rating-card__valor">${fmtInt.format(s.last.rating)}</div>
        <div class="rating-card__extra">recorde ${s.best ? fmtInt.format(s.best.rating) : "—"} · ${rec.win ?? 0}V ${rec.draw ?? 0}E ${rec.loss ?? 0}D</div>
      </div>`;
    }).join("");
  }

  // ---------- Filtros ----------
  function aplicarPreset(chave) {
    const hoje = hojeISO();
    estado.periodo = chave;
    estado.ate = chave === "tudo" ? "" : hoje;
    estado.de = { tudo: "", ano: hoje.slice(0, 4) + "-01-01", "12m": somaDias(hoje, -365), "90d": somaDias(hoje, -90), "30d": somaDias(hoje, -30) }[chave] ?? "";
    $("data-de").value = estado.de;
    $("data-ate").value = estado.ate;
  }

  function montarChips(id, opcoes, chaveEstado, aoMudar) {
    const el = $(id);
    el.innerHTML = opcoes.map((o) =>
      `<button type="button" class="chip" data-v="${o.chave}" aria-pressed="${estado[chaveEstado] === o.chave}">${o.ponto ? `<span class="ponto" style="background:var(--${o.chave})"></span>` : ""}${esc(o.nome)}</button>`).join("");
    el.addEventListener("click", (ev) => {
      const b = ev.target.closest(".chip");
      if (!b) return;
      aoMudar ? aoMudar(b.dataset.v) : (estado[chaveEstado] = b.dataset.v);
      marcarChips(id, estado[chaveEstado]);
      renderizar();
    });
  }
  const marcarChips = (id, v) => $(id).querySelectorAll(".chip").forEach((b) => b.setAttribute("aria-pressed", b.dataset.v === v));

  function filtradas(opts = {}) {
    return TODAS.filter((p) =>
      (estado.ritmo === "todos" || p.ritmo === estado.ritmo) &&
      (opts.semPeriodo || ((!estado.de || p.data >= estado.de) && (!estado.ate || p.data <= estado.ate))));
  }

  function iniciarFiltros() {
    const presentes = RITMOS.filter((r) => TODAS.some((p) => p.ritmo === r));
    montarChips("filtro-ritmo", [{ chave: "todos", nome: "Todos" }, ...presentes.map((r) => ({ chave: r, nome: NOME_RITMO[r], ponto: true }))], "ritmo");
    montarChips("filtro-periodo", PERIODOS, "periodo", aplicarPreset);
    const aoDigitar = () => {
      estado.de = $("data-de").value; estado.ate = $("data-ate").value; estado.periodo = "custom";
      marcarChips("filtro-periodo", "custom");
      renderizar();
    };
    $("data-de").addEventListener("change", aoDigitar);
    $("data-ate").addEventListener("change", aoDigitar);
    $("data-de").min = $("data-ate").min = TODAS[0].data;
    $("data-de").max = $("data-ate").max = hojeISO();

    montarChips("aberturas-nivel", [{ chave: "familia", nome: "Família" }, { chave: "abertura", nome: "Variante" }], "abNivel");
    montarChips("aberturas-cor", [{ chave: "todas", nome: "Ambas as cores" }, { chave: "brancas", nome: "Brancas" }, { chave: "pretas", nome: "Pretas" }], "abCor");
    $("mais-recentes").addEventListener("click", () => { estado.recentesN += 20; renderRecentes(filtradas()); });
  }

  // ---------- Gráficos (Chart.js) ----------
  function prepararChart() {
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.color = css("--texto-suave");
    Chart.defaults.borderColor = css("--borda");
    Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.animation = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : { duration: 250 };
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.boxHeight = 8;
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.cornerRadius = 8;
  }

  function desenhar(id, config) {
    if (graficos[id]) graficos[id].destroy();
    graficos[id] = new Chart($(id), config);
  }

  // Barras empilhadas V/E/D. modo "pct": 100% empilhado; "n": contagens.
  function graficoVED(id, rotulos, grupos, modo, extra = {}) {
    const superficie = css("--superficie");
    const datasets = RESULTADOS.map((r) => ({
      label: r.nome,
      data: grupos.map((g) => (modo === "pct" ? (g.n ? (g[r.chave] / g.n) * 100 : 0) : g[r.chave])),
      backgroundColor: css(r.cor),
      borderColor: superficie, borderWidth: { top: 2, bottom: 0, left: 0, right: 0 },
      borderSkipped: false, maxBarThickness: 44, categoryPercentage: 0.8, barPercentage: 0.9,
    }));
    desenhar(id, {
      type: "bar",
      data: { labels: rotulos, datasets },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { stacked: true, grid: { display: false }, title: extra.tituloX ? { display: true, text: extra.tituloX } : undefined },
          y: { stacked: true, max: modo === "pct" ? 100 : undefined, grid: { color: css("--borda") }, border: { display: false },
               ticks: { callback: (v) => (modo === "pct" ? v + "%" : fmtInt.format(v)), maxTicksLimit: 6 } },
        },
        plugins: {
          legend: { position: "top", align: "end" },
          tooltip: {
            callbacks: {
              title: (it) => { const g = grupos[it[0].dataIndex]; return `${[].concat(rotulos[it[0].dataIndex]).join(" ")} — ${fmtInt.format(g.n)} partidas`; },
              label: (it) => { const g = grupos[it.dataIndex]; const k = RESULTADOS[it.datasetIndex].chave; return ` ${it.dataset.label}: ${pct(g.n ? g[k] / g.n : NaN)} (${g[k]})`; },
              footer: (it) => { const g = grupos[it[0].dataIndex]; return g.n ? `Pontuação: ${pct(g.pontos)}` : ""; },
            },
          },
        },
      },
    });
  }

  // Barras horizontais de uma série só
  function graficoBarrasH(id, rotulos, valores, corVar, total) {
    const area = $(id).parentElement;
    area.style.height = Math.max(90, rotulos.length * 34 + 30) + "px";
    desenhar(id, {
      type: "bar",
      data: { labels: rotulos, datasets: [{ data: valores, backgroundColor: css(corVar), borderRadius: 4, borderSkipped: "start", maxBarThickness: 22 }] },
      options: {
        indexAxis: "y",
        scales: { x: { grid: { color: css("--borda") }, border: { display: false }, ticks: { precision: 0, maxTicksLimit: 6 } }, y: { grid: { display: false } } },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (it) => ` ${fmtInt.format(it.raw)} (${pct(it.raw / total)})` } },
        },
      },
    });
  }

  // ---------- Seções ----------
  function renderKPIs(ps) {
    const c = contar(ps);
    const tiles = [
      { rotulo: "Partidas", valor: fmtInt.format(c.n), extra: c.n ? `${fmtData(ps[0].data)} a ${fmtData(ps[ps.length - 1].data)}` : "" },
      ...RESULTADOS.map((r) => ({ rotulo: `<span class="quad" style="background:var(${r.cor})"></span>${r.nome}`, valor: pct(c[r.chave] / c.n), extra: `${fmtInt.format(c[r.chave])} partidas` })),
      { rotulo: "Pontuação", valor: pct(c.pontos), extra: "vitória = 1, empate = ½" },
    ];
    if (estado.ritmo !== "todos") {
      const rat = ps.filter((p) => p.ranqueada && p.variante === "chess" && p.meu_rating);
      if (rat.length) {
        const ini = rat[0].meu_rating, fim = rat[rat.length - 1].meu_rating, d = fim - ini;
        tiles.push({ rotulo: "Rating no fim do período", valor: fmtInt.format(fim), extra: `${d >= 0 ? "+" : "−"}${Math.abs(d)} no período · pico ${Math.max(...rat.map((p) => p.meu_rating))}` });
      }
    }
    const comAcc = ps.filter((p) => p.precisao != null);
    if (comAcc.length) {
      const m = comAcc.reduce((s, p) => s + p.precisao, 0) / comAcc.length;
      tiles.push({ rotulo: "Precisão média", valor: m.toFixed(1).replace(".", ","), extra: `em ${comAcc.length} partidas analisadas` });
    }
    $("kpis").innerHTML = tiles.map((t) => `<div class="kpi"><div class="kpi__rotulo">${t.rotulo}</div><div class="kpi__valor">${t.valor}</div><div class="kpi__extra">${t.extra}</div></div>`).join("");
  }

  function renderRating(ps) {
    const series = RITMOS.filter((r) => estado.ritmo === "todos" || r === estado.ritmo).map((r) => ({
      r, pontos: ps.filter((p) => p.ritmo === r && p.ranqueada && p.variante === "chess" && p.meu_rating).map((p) => ({ x: p.ts, y: p.meu_rating, p })),
    })).filter((s) => s.pontos.length);
    // Intervalos longos sem jogar quebram a linha (em vez de uma reta que parece dado)
    const comQuebras = (pts) => pts.flatMap((pt, i) => (i && pt.x - pts[i - 1].x > PAUSA_LONGA_MS ? [{ x: pt.x - 1, y: null }, pt] : [pt]));
    const superficie = css("--superficie");
    desenhar("g-rating", {
      type: "line",
      data: {
        datasets: series.map((s) => ({
          label: NOME_RITMO[s.r], data: comQuebras(s.pontos), borderColor: css(`--${s.r}`), backgroundColor: css(`--${s.r}`),
          borderWidth: 2,
          pointRadius: (ctx) => {   // ponto só em séries curtas ou em partidas isoladas entre pausas
            if (s.pontos.length < 30) return 3;
            const d = ctx.dataset.data, i = ctx.dataIndex;
            return d[i] && d[i].y != null && (!d[i - 1] || d[i - 1].y == null) && (!d[i + 1] || d[i + 1].y == null) ? 3 : 0;
          }, pointHoverRadius: 5, pointBorderColor: superficie, pointBorderWidth: 2,
          tension: 0.15, spanGaps: false,
        })),
      },
      options: {
        parsing: false, normalized: true,
        interaction: { mode: "nearest", axis: "x", intersect: false },
        scales: {
          x: { type: "linear", grid: { display: false }, ticks: { callback: (v) => fmtMes(v), maxTicksLimit: 8, maxRotation: 0 } },
          y: { grid: { color: css("--borda") }, border: { display: false }, ticks: { maxTicksLimit: 6 } },
        },
        plugins: {
          legend: { display: series.length > 1, position: "top", align: "end" },
          tooltip: {
            callbacks: {
              title: (it) => new Date(it[0].raw.x).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }),
              label: (it) => { const p = it.raw.p; if (!p) return ""; return ` ${it.dataset.label}: ${p.meu_rating} — ${p.resultado === "vitoria" ? "venceu" : p.resultado === "derrota" ? "perdeu" : "empatou"} vs ${p.adversario} (${p.adv_rating})`; },
            },
          },
        },
      },
    });
    tabelaDados("t-rating", ["Ritmo", "Partidas", "Inicial", "Final", "Mínimo", "Máximo"],
      series.map((s) => { const y = s.pontos.map((p) => p.y); return [NOME_RITMO[s.r], s.pontos.length, y[0], y[y.length - 1], Math.min(...y), Math.max(...y)]; }));
  }

  function renderCor(ps) {
    const geral = contar(ps);
    const linhas = [["brancas", "Brancas"], ["pretas", "Pretas"]].map(([k, nome]) => {
      const c = contar(ps.filter((p) => p.cor === k));
      return `<div style="margin-top:16px">
        <div style="display:flex;justify-content:space-between;gap:8px;font-size:.9rem"><strong><span class="peca peca--${k}"></span>${nome}</strong><span style="color:var(--texto-suave)">${fmtInt.format(c.n)} partidas · pontuação ${pct(c.pontos)}</span></div>
        ${barraVED(c, true)}${legendaVED(c)}</div>`;
    }).join("");
    $("card-cor").innerHTML = `<h3>Geral e por cor</h3><p class="nota">${fmtInt.format(geral.n)} partidas no período.</p>
      ${barraVED(geral, true)}${legendaVED(geral)}${linhas}`;
  }

  function renderForca(ps) {
    const grupos = FAIXAS_FORCA.map(() => []);
    for (const p of ps) {
      if (p.meu_rating == null || p.adv_rating == null) continue;
      const d = p.adv_rating - p.meu_rating;
      grupos[FAIXAS_FORCA.findIndex((f) => d < f.ate)].push(p);
    }
    const cs = grupos.map(contar);
    graficoVED("g-forca", FAIXAS_FORCA.map((f, i) => [f.nome, `n=${cs[i].n}`]), cs, "pct", { tituloX: "← adversário mais fraco · mais forte →" });
    tabelaDados("t-forca", ["Diferença de rating", "Partidas", "Vitórias", "Empates", "Derrotas", "Pontuação"],
      FAIXAS_FORCA.map((f, i) => [f.nome, cs[i].n, cs[i].vitoria, cs[i].empate, cs[i].derrota, pct(cs[i].pontos)]));
  }

  function renderAberturas(ps) {
    const campo = estado.abNivel === "familia" ? "familia" : "abertura";
    const base = ps.filter((p) => p.variante === "chess" && (estado.abCor === "todas" || p.cor === estado.abCor));
    const grupos = new Map();
    for (const p of base) {
      const k = p[campo] || "Não identificada";
      if (!grupos.has(k)) grupos.set(k, []);
      grupos.get(k).push(p);
    }
    const top = [...grupos.entries()].map(([nome, lista]) => {
      const ecos = {};
      lista.forEach((p) => p.eco && (ecos[p.eco] = (ecos[p.eco] || 0) + 1));
      const eco = Object.entries(ecos).sort((a, b) => b[1] - a[1]).map((e) => e[0]).slice(0, 2).join(", ");
      return { nome, eco, c: contar(lista) };
    }).sort((a, b) => b.c.n - a.c.n || b.c.pontos - a.c.pontos).slice(0, 15);

    if (!top.length) { $("tabela-aberturas").innerHTML = `<p class="vazio">Sem partidas no filtro atual.</p>`; return; }
    $("tabela-aberturas").innerHTML = `<table>
      <thead><tr><th>Abertura</th><th>ECO</th><th class="num">Partidas</th><th style="min-width:160px">Resultado</th><th class="num">Vitórias</th><th class="num">Pontuação</th></tr></thead>
      <tbody>${top.map((a) => `<tr>
        <td class="abertura-nome">${esc(a.nome)}</td><td>${esc(a.eco)}</td><td class="num">${a.c.n}</td>
        <td>${barraVED(a.c)}</td><td class="num">${pct(a.c.vitoria / a.c.n)}</td><td class="num">${pct(a.c.pontos)}</td></tr>`).join("")}
      </tbody></table>${legendaVED()}`;
  }

  function renderFim(ps) {
    const blocos = { vitoria: {}, derrota: {}, empate: {} };
    ps.forEach((p) => (blocos[p.resultado][p.motivo] = (blocos[p.resultado][p.motivo] || 0) + 1));
    [["vitoria", "g-fim-vit", "t-fim-vit", "--vitoria"], ["derrota", "g-fim-der", "t-fim-der", "--derrota"]].forEach(([res, g, t, cor]) => {
      const ent = Object.entries(blocos[res]).sort((a, b) => b[1] - a[1]);
      const total = ent.reduce((s, e) => s + e[1], 0);
      graficoBarrasH(g, ent.map((e) => MOTIVOS[e[0]] || e[0]), ent.map((e) => e[1]), cor, total);
      tabelaDados(t, ["Motivo", "Partidas", "%"], ent.map((e) => [MOTIVOS[e[0]] || e[0], e[1], pct(e[1] / total)]));
    });
    const emp = Object.entries(blocos.empate).sort((a, b) => b[1] - a[1]);
    const nEmp = emp.reduce((s, e) => s + e[1], 0);
    $("desc-empates").textContent = nEmp
      ? `Empates (${nEmp}): ${emp.map((e) => `${(MOTIVOS[e[0]] || e[0]).toLowerCase()} ${e[1]}`).join(", ")}.`
      : "Nenhum empate no período.";
  }

  function renderQuando(ps) {
    const porDia = DIAS.map((_, i) => contar(ps.filter((p) => p.dia_semana === i)));
    const porHora = Array.from({ length: 24 }, (_, h) => contar(ps.filter((p) => p.hora === h)));
    graficoVED("g-dia", DIAS, porDia, "n");
    graficoVED("g-hora", porHora.map((_, h) => `${h}h`), porHora, "n");
    tabelaDados("t-dia", ["Dia", "Partidas", "Vitórias", "Empates", "Derrotas", "Pontuação"], porDia.map((c, i) => [DIAS[i], c.n, c.vitoria, c.empate, c.derrota, pct(c.pontos)]));
    tabelaDados("t-hora", ["Hora", "Partidas", "Vitórias", "Empates", "Derrotas", "Pontuação"], porHora.map((c, h) => [`${h}h`, c.n, c.vitoria, c.empate, c.derrota, pct(c.pontos)]).filter((l) => l[1]));

    const minimo = Math.max(5, Math.round(ps.length * 0.05));
    const dias = porDia.map((c, i) => ({ c, i })).filter((d) => d.c.n >= minimo).sort((a, b) => b.c.pontos - a.c.pontos);
    const horas = porHora.map((c, h) => ({ c, h })).filter((d) => d.c.n >= minimo).sort((a, b) => b.c.pontos - a.c.pontos);
    const partes = [];
    if (dias.length >= 2) partes.push(`Melhor dia: ${DIAS_LONGOS[dias[0].i]} (${pct(dias[0].c.pontos)} de pontuação); pior: ${DIAS_LONGOS[dias[dias.length - 1].i]} (${pct(dias[dias.length - 1].c.pontos)}).`);
    if (horas.length >= 2) partes.push(`Melhor horário: ${horas[0].h}h (${pct(horas[0].c.pontos)}); pior: ${horas[horas.length - 1].h}h (${pct(horas[horas.length - 1].c.pontos)}).`);
    $("desc-quando").textContent = (partes.join(" ") || "Volume de partidas e resultado por dia e hora.") + ` Considera só grupos com pelo menos ${minimo} partidas.`;
  }

  function renderSequencias(ps) {
    let atual = null, tam = 0, melhor = { vitoria: { n: 0 }, derrota: { n: 0 } }, ini = null;
    for (const p of ps) {
      if (p.resultado === atual) tam++; else { atual = p.resultado; tam = 1; ini = p; }
      if (melhor[atual] && tam > melhor[atual].n) melhor[atual] = { n: tam, de: ini.data, ate: p.data };
    }
    // "Efeito tilt": resultado da partida seguinte (até 1h depois, mesmo ritmo)
    const apos = { vitoria: [], derrota: [] };
    for (let i = 1; i < ps.length; i++) {
      const a = ps[i - 1], b = ps[i];
      if (a.ritmo === b.ritmo && b.ts - a.ts <= INTERVALO_SESSAO_MS && apos[a.resultado]) apos[a.resultado].push(b);
    }
    const cV = contar(apos.vitoria), cD = contar(apos.derrota);
    const nomeSeq = { vitoria: "vitória", derrota: "derrota", empate: "empate" };
    const periodo = (m) => (m.n ? (m.de === m.ate ? fmtData(m.de) : `${fmtData(m.de)} a ${fmtData(m.ate)}`) : "—");
    const tiles = [
      { r: "Maior sequência de vitórias", cor: "--vitoria", v: melhor.vitoria.n, e: periodo(melhor.vitoria) },
      { r: "Maior sequência de derrotas", cor: "--derrota", v: melhor.derrota.n, e: periodo(melhor.derrota) },
      { r: "Sequência atual", v: ps.length ? `${tam} ${nomeSeq[atual]}${tam > 1 ? "s" : ""}` : "—", e: ps.length ? `desde ${fmtData(ini.data)}` : "" },
      { r: "Depois de uma vitória", v: pct(cV.pontos), e: `pontuação na partida seguinte (${cV.n})` },
      { r: "Depois de uma derrota", v: pct(cD.pontos), e: `pontuação na partida seguinte (${cD.n})` },
    ];
    $("sequencias").innerHTML = tiles.map((t) => `<div class="kpi"><div class="kpi__rotulo">${t.cor ? `<span class="quad" style="background:var(${t.cor})"></span>` : ""}${t.r}</div><div class="kpi__valor">${t.v}</div><div class="kpi__extra">${t.e}</div></div>`).join("");
  }

  function nivelHeat(n) { return n === 0 ? 0 : n === 1 ? 1 : n <= 3 ? 2 : n <= 6 ? 3 : n <= 10 ? 4 : 5; }

  function renderHeatmap() {
    const ps = filtradas({ semPeriodo: true });
    const fim = estado.ate && estado.ate < hojeISO() ? estado.ate : hojeISO();
    const dFim = new Date(fim + "T12:00:00");
    const inicio = somaDias(fim, -(52 * 7 + ((dFim.getDay() + 6) % 7)));   // segunda-feira, 53 semanas
    const porDia = new Map();
    for (const p of ps) {
      if (p.data < inicio || p.data > fim) continue;
      if (!porDia.has(p.data)) porDia.set(p.data, []);
      porDia.get(p.data).push(p);
    }
    const partes = [`<span></span>`, ...["Seg", "", "Qua", "", "Sex", "", ""].map((d) => `<span class="heatmap__dia-rotulo">${d}</span>`)];
    let dia = inicio, semana = 0, ultimoMes = "";
    while (dia <= fim) {
      const mes = dia.slice(0, 7);
      const rotuloMes = mes !== ultimoMes && dia.slice(8) <= "07"
        ? new Date(dia + "T12:00:00").toLocaleDateString("pt-BR", { month: "short" }).replace(".", "") : "";
      if (rotuloMes) ultimoMes = mes;
      partes.push(`<span class="heatmap__mes" style="grid-column:${semana + 2}">${rotuloMes}</span>`);
      for (let d = 0; d < 7; d++) {
        const lista = porDia.get(dia) || [];
        if (dia > fim) partes.push(`<span class="cel cel--fora" style="grid-column:${semana + 2};grid-row:${d + 2}"></span>`);
        else {
          const c = contar(lista);
          const txt = `${fmtData(dia)} — ${lista.length ? `${c.n} partida${c.n > 1 ? "s" : ""} (${c.vitoria}V ${c.empate}E ${c.derrota}D)` : "nenhuma partida"}`;
          partes.push(`<span class="cel" data-n="${nivelHeat(lista.length)}" data-dica="${txt}" style="grid-column:${semana + 2};grid-row:${d + 2}"></span>`);
        }
        dia = somaDias(dia, 1);
      }
      semana++;
    }
    const el = $("heatmap");
    el.innerHTML = partes.join("");
    el.style.gridTemplateColumns = `auto repeat(${semana}, 12px)`;
    el.setAttribute("role", "img");
    el.setAttribute("aria-label", `Partidas por dia de ${fmtData(inicio)} a ${fmtData(fim)}: ${[...porDia.values()].reduce((s, l) => s + l.length, 0)} partidas em ${porDia.size} dias.`);
    el.parentElement.scrollLeft = el.scrollWidth;
    $("heatmap-legenda").innerHTML = `${[...porDia.values()].reduce((s, l) => s + l.length, 0)} partidas em ${porDia.size} dias &nbsp;·&nbsp; menos ${
      [0, 1, 2, 3, 4, 5].map((n) => `<span class="cel" data-n="${n}" title="${["0", "1", "2–3", "4–6", "7–10", "11+"][n]}"></span>`).join("")} mais`;
  }

  function renderTempo(ps) {
    const vivas = ps.filter((p) => p.relogio_final != null);
    const nota = $("nota-tempo");
    if (!vivas.length) {
      nota.textContent = "Sem partidas ao vivo com relógio no filtro atual.";
      if (graficos["g-tempo"]) { graficos["g-tempo"].destroy(); delete graficos["g-tempo"]; }
      $("card-apuro").innerHTML = `<h3>Apuro de tempo</h3><p class="vazio">Sem dados.</p>`;
      $("t-tempo").innerHTML = "<summary>Ver dados</summary>";
      return;
    }
    const ritmos = new Set(vivas.map((p) => p.ritmo));
    nota.textContent = ritmos.size > 1
      ? "Misturando ritmos com tempos diferentes — selecione um ritmo para comparar melhor."
      : `Segundos gastos em média por lance seu, ${NOME_RITMO[[...ritmos][0]]}.`;
    const media = (lista, k) => { const v = lista.map((p) => p[k]).filter((x) => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
    const grupos = RESULTADOS.filter((r) => r.chave !== "empate").map((r) => ({ r, lista: vivas.filter((p) => p.resultado === r.chave) }));
    desenhar("g-tempo", {
      type: "bar",
      data: {
        labels: FASES.map((f) => f.nome),
        datasets: grupos.map((g) => ({ label: `Nas ${g.r.nome.toLowerCase()}`, data: FASES.map((f) => media(g.lista, f.chave)), backgroundColor: css(g.r.cor), borderRadius: 4, borderSkipped: "start", maxBarThickness: 36 })),
      },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: { x: { grid: { display: false } }, y: { grid: { color: css("--borda") }, border: { display: false }, ticks: { callback: (v) => v + "s", maxTicksLimit: 6 } } },
        plugins: { legend: { position: "top", align: "end" }, tooltip: { callbacks: { label: (it) => ` ${it.dataset.label}: ${it.raw == null ? "—" : it.raw.toFixed(1).replace(".", ",") + "s por lance"}` } } },
      },
    });
    tabelaDados("t-tempo", ["Fase", ...grupos.map((g) => `Nas ${g.r.nome.toLowerCase()} (s)`)],
      FASES.map((f) => [f.nome, ...grupos.map((g) => { const m = media(g.lista, f.chave); return m == null ? "—" : m.toFixed(1).replace(".", ","); })]));

    const comApuro = vivas.filter((p) => p.apuro), semApuro = vivas.filter((p) => !p.apuro);
    const cA = contar(comApuro), cS = contar(semApuro);
    const vitTempo = vivas.filter((p) => p.resultado === "vitoria" && p.motivo === "tempo").length;
    const derTempo = vivas.filter((p) => p.resultado === "derrota" && p.motivo === "tempo").length;
    const restoMedio = (res) => media(vivas.filter((p) => p.resultado === res), "relogio_final");
    $("card-apuro").innerHTML = `<h3>Apuro de tempo</h3>
      <p class="nota">Apuro = ficar com menos de 10% do tempo-base em algum momento da partida.</p>
      <div class="kpis" style="grid-template-columns:repeat(auto-fit,minmax(140px,1fr))">
        <div class="kpi"><div class="kpi__rotulo">Partidas com apuro</div><div class="kpi__valor">${pct(comApuro.length / vivas.length)}</div><div class="kpi__extra">${comApuro.length} de ${vivas.length}</div></div>
        <div class="kpi"><div class="kpi__rotulo">Pontuação com apuro</div><div class="kpi__valor">${pct(cA.pontos)}</div><div class="kpi__extra">sem apuro: ${pct(cS.pontos)}</div></div>
        <div class="kpi"><div class="kpi__rotulo">Decididas no relógio</div><div class="kpi__valor">${vitTempo} / ${derTempo}</div><div class="kpi__extra">vitórias / derrotas por tempo</div></div>
        <div class="kpi"><div class="kpi__rotulo">Relógio restante no fim</div><div class="kpi__valor">${pct(restoMedio("vitoria"))}</div><div class="kpi__extra">nas vitórias · ${pct(restoMedio("derrota"))} nas derrotas</div></div>
      </div>`;
  }

  function renderRecentes(ps) {
    const lista = ps.slice().reverse().slice(0, estado.recentesN);
    const nomeRes = { vitoria: "Vitória", derrota: "Derrota", empate: "Empate" };
    $("tabela-recentes").innerHTML = lista.length ? `<table>
      <thead><tr><th>Data</th><th>Ritmo</th><th>Cor</th><th>Adversário</th><th class="num">Seu rating</th><th>Resultado</th><th>Motivo</th><th>Abertura</th><th class="num">Lances</th><th class="num">Precisão</th><th></th></tr></thead>
      <tbody>${lista.map((p) => `<tr>
        <td>${fmtData(p.data)} ${String(p.hora).padStart(2, "0")}h</td>
        <td><span class="ponto" style="background:var(--${p.ritmo})"></span> ${NOME_RITMO[p.ritmo] || p.ritmo} <span style="color:var(--texto-suave)">${esc(fmtControle(p.controle))}</span>${p.variante !== "chess" ? ` <span style="color:var(--texto-suave)">(${esc(p.variante)})</span>` : ""}</td>
        <td><span class="peca peca--${p.cor}" title="${p.cor}"></span>${p.cor === "brancas" ? "Brancas" : "Pretas"}</td>
        <td><a href="https://www.chess.com/member/${encodeURIComponent(p.adversario)}" target="_blank" rel="noopener">${esc(p.adversario)}</a> <span style="color:var(--texto-suave)">(${p.adv_rating ?? "—"})</span></td>
        <td class="num">${p.meu_rating ?? "—"}</td>
        <td><span class="badge badge--${p.resultado}">${nomeRes[p.resultado]}</span></td>
        <td>${esc(MOTIVOS[p.motivo] || p.motivo)}</td>
        <td class="abertura-nome">${esc(p.abertura || "—")}</td>
        <td class="num">${p.lances}</td>
        <td class="num">${p.precisao != null ? p.precisao.toFixed(1).replace(".", ",") : "—"}</td>
        <td><a href="${esc(p.url)}" target="_blank" rel="noopener">Abrir ↗</a></td></tr>`).join("")}</tbody></table>`
      : `<p class="vazio">Sem partidas no filtro atual.</p>`;
    $("mais-recentes").hidden = ps.length <= estado.recentesN;
  }

  // ---------- Orquestração ----------
  function renderizar() {
    prepararChart();
    const ps = filtradas();
    const c = contar(ps);
    $("resumo-filtro").textContent = `${fmtInt.format(c.n)} partidas no filtro`;
    renderKPIs(ps);
    renderRating(ps);
    renderCor(ps);
    renderForca(ps);
    renderAberturas(ps);
    renderFim(ps);
    renderQuando(ps);
    renderSequencias(ps);
    renderHeatmap();
    renderTempo(ps);
    renderRecentes(ps);
  }

  // ---------- Tema ----------
  function iniciarTema() {
    const botoes = document.querySelectorAll("#tema-switch .tema-switch__btn");
    const escuroSistema = window.matchMedia("(prefers-color-scheme: dark)");
    const atual = () => document.documentElement.getAttribute("data-theme") || (escuroSistema.matches ? "dark" : "light");
    const marcar = () => botoes.forEach((b) => b.setAttribute("aria-pressed", b.dataset.tema === atual()));
    botoes.forEach((b) => b.addEventListener("click", () => {
      document.documentElement.setAttribute("data-theme", b.dataset.tema);
      try { localStorage.setItem("tema", b.dataset.tema); } catch (e) { /* armazenamento indisponível */ }
      marcar();
      if (TODAS.length) renderizar();
    }));
    escuroSistema.addEventListener("change", () => { marcar(); if (TODAS.length) renderizar(); });
    marcar();
  }

  // Dica flutuante do heatmap
  function iniciarDica() {
    const dica = $("dica");
    document.addEventListener("mouseover", (ev) => {
      const alvo = ev.target.closest("[data-dica]");
      if (!alvo) { dica.classList.remove("visivel"); return; }
      dica.textContent = alvo.dataset.dica;
      const r = alvo.getBoundingClientRect();
      dica.classList.add("visivel");
      const w = dica.offsetWidth;
      dica.style.left = Math.min(window.innerWidth - w - 8, Math.max(8, r.left + r.width / 2 - w / 2)) + "px";
      dica.style.top = r.top - dica.offsetHeight - 8 + "px";
    });
  }

  iniciarTema();
  iniciarDica();
  carregar().then(() => {
    renderCabecalho();
    iniciarFiltros();
    renderizar();
  }).catch((e) => {
    console.error(e);
    $("nome-usuario").textContent = "Erro ao carregar os dados";
    $("meta-gerado").textContent = String(e.message || e);
  });
})();
