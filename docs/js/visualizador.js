/* ===== Chess Tracking — visualizador lance a lance =====
   Abre uma partida num <dialog>: tabuleiro (chessground, do Lichess), relógios,
   saldo de material, lista de lances com a classificação do motor, comentário do
   lance atual, resumo de erros/precisão e gráfico da partida (clique para pular).
   Os dados vêm de docs/dados/jogos/AAAA-MM.json, carregado só quando preciso. */
(function () {
  "use strict";

  const CG_VERSAO = "10.4.0";
  const CG_BASE = `https://cdn.jsdelivr.net/npm/@lichess-org/chessground@${CG_VERSAO}`;
  const MATE = 10000;
  const MARCA = { imprecisao: "?!", erro: "?", erro_grave: "??", melhor: "★" };
  const NOME_CLASSE = { imprecisao: "Imprecisão", erro: "Erro", erro_grave: "Erro grave", melhor: "Melhor lance" };
  const RES_TEXTO = { vitoria: "Vitória", derrota: "Derrota", empate: "Empate" };

  const $ = (id) => document.getElementById(id);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const cacheMeses = new Map();
  let Chessground = null;
  let cg = null, grafico = null;
  let jogo = null, partida = null, ply = 0, orientacao = "white";

  // ---------- Utilidades de xadrez ----------
  const ehMate = (v) => Math.abs(v) > MATE - 1000;
  const chance = (v) => (ehMate(v) ? (v > 0 ? 100 : 0) : 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * v)) - 1));
  function fmtAval(v) {
    if (ehMate(v)) { const n = MATE - Math.abs(v); return n ? (v > 0 ? "#" : "#-") + n : (v > 0 ? "1-0" : "0-1"); }
    return (v >= 0 ? "+" : "−") + (Math.abs(v) / 100).toFixed(1).replace(".", ",");
  }
  function fmtRelogio(s) {
    if (s == null) return "—";
    if (s >= 86400) return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`;
    if (s >= 3600) return `${Math.floor(s / 3600)}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
    const m = Math.floor(s / 60), r = s - m * 60;
    return s < 20 ? `${m}:${r.toFixed(1).padStart(4, "0")}` : `${m}:${String(Math.floor(r)).padStart(2, "0")}`;
  }
  function tempoBase(ctrl) {
    if (!ctrl || ctrl.includes("/")) return null;
    return +ctrl.split("+")[0];
  }
  const numeroLance = (i) => `${Math.floor(i / 2) + 1}${i % 2 ? "…" : "."}`;

  // ---------- Carregamento ----------
  async function carregarChessground() {
    if (Chessground) return;
    for (const f of ["chessground.base.css", "chessground.brown.css", "chessground.cburnett.css"]) {
      const l = document.createElement("link");
      l.rel = "stylesheet"; l.href = `${CG_BASE}/assets/${f}`;
      document.head.appendChild(l);
    }
    ({ Chessground } = await import(`${CG_BASE}/dist/chessground.min.js`));
  }

  async function carregarMes(mes) {
    if (!cacheMeses.has(mes)) {
      cacheMeses.set(mes, fetch(`dados/jogos/${mes}.json`, { cache: "no-cache" }).then((r) => {
        if (!r.ok) throw new Error(`dados/jogos/${mes}.json: HTTP ${r.status}`);
        return r.json();
      }));
    }
    try { return await cacheMeses.get(mes); } catch (e) { cacheMeses.delete(mes); throw e; }
  }

  // ---------- Render ----------
  const minhaCor = () => (partida.cor === "brancas" ? "white" : "black");
  const temAnalise = () => Array.isArray(jogo.av);

  function relogioDe(cor, k) {
    const par = cor === "white" ? 0 : 1;
    for (let i = k - 1; i >= 0; i--) if (i % 2 === par && jogo.clk[i] != null) return jogo.clk[i];
    return tempoBase(partida.controle);
  }

  function renderJogadores() {
    const app = window.ChessApp;
    const eu = { nome: app.usuario, rating: partida.meu_rating, cor: minhaCor() };
    const adv = { nome: partida.adversario, rating: partida.adv_rating, cor: minhaCor() === "white" ? "black" : "white" };
    const saldo = ply ? jogo.sal[ply - 1] : 0;
    const vez = ply % 2 === 0 ? "white" : "black";
    const bloco = (j, sal) => `<span><span class="peca peca--${j.cor === "white" ? "brancas" : "pretas"}"></span><strong>${esc(j.nome)}</strong> <span style="color:var(--texto-suave)">(${j.rating ?? "—"})</span>${sal > 0 ? `<span class="saldo">+${sal}</span>` : ""}</span>
      <span class="relogio${vez === j.cor && ply < jogo.san.length ? " relogio--ativo" : ""}">${fmtRelogio(relogioDe(j.cor, ply))}</span>`;
    const [topo, base] = orientacao === minhaCor() ? [adv, eu] : [eu, adv];
    $("vis-jog-topo").innerHTML = bloco(topo, topo === eu ? saldo : -saldo);
    $("vis-jog-base").innerHTML = bloco(base, base === eu ? saldo : -saldo);
  }

  function renderTabuleiro() {
    const fen = ply ? jogo.fen[ply - 1] : jogo.fi;
    const uci = ply ? jogo.uci[ply - 1] : null;
    const san = ply ? jogo.san[ply - 1] : "";
    const formas = [];
    if (ply && temAnalise()) {
      const cl = jogo.cl[ply - 1], mu = jogo.mu && jogo.mu[ply - 1];
      if (["imprecisao", "erro", "erro_grave"].includes(cl) && mu && mu !== uci) {
        formas.push({ orig: mu.slice(0, 2), dest: mu.slice(2, 4), brush: "green" });
      }
    }
    cg.set({
      fen, orientation: orientacao,
      lastMove: uci ? [uci.slice(0, 2), uci.slice(2, 4)] : undefined,
      check: /[+#]/.test(san) ? (ply % 2 === 0 ? "white" : "black") : false,
      drawable: { autoShapes: formas },
    });
    const barra = $("vis-barra");
    if (temAnalise()) {
      barra.hidden = false;
      const v = jogo.av[ply];
      $("vis-barra-b").style.height = chance(v) + "%";
      barra.classList.toggle("invertida", orientacao === "black");
      $("vis-barra-txt").textContent = fmtAval(v);
    } else barra.hidden = true;
  }

  function renderComentario() {
    const app = window.ChessApp;
    const el = $("vis-comentario");
    if (!ply) {
      el.innerHTML = `<strong>Posição inicial</strong>${esc(partida.abertura || "")}${partida.eco ? ` (${esc(partida.eco)})` : ""}.
        <br><span style="color:var(--texto-suave)">Use ← → no teclado, os botões ou clique num lance.</span>`;
      return;
    }
    const i = ply - 1;
    const cl = temAnalise() ? jogo.cl[i] : "";
    let html = `<strong>${numeroLance(i)} ${esc(jogo.san[i])} ${cl && MARCA[cl] ? `<span class="cl-${cl}">${MARCA[cl]} ${NOME_CLASSE[cl]}</span>` : ""}</strong>`;
    if (temAnalise()) {
      const txt = jogo.cm[i];
      const v = jogo.av[ply];
      const lado = Math.abs(v) < 30 ? "posição equilibrada" : `vantagem das ${v > 0 ? "brancas" : "pretas"}`;
      html += txt ? esc(txt) : `<span style="color:var(--texto-suave)">Lance sem observações. Avaliação ${fmtAval(v)} (${lado}).</span>`;
    } else {
      html += `<span style="color:var(--texto-suave)">Partida ainda sem análise do motor — ela é feita aos poucos pela atualização diária.</span>`;
    }
    if (ply === jogo.san.length) {
      html += `<br><strong style="margin-top:6px">Fim: ${RES_TEXTO[partida.resultado]} — ${esc((app.MOTIVOS[partida.motivo] || partida.motivo).toLowerCase())}.</strong>`;
    }
    el.innerHTML = html;
  }

  function renderLances() {
    const el = $("vis-lances");
    const partes = [];
    for (let i = 0; i < jogo.san.length; i += 2) {
      partes.push(`<span class="num-lance">${i / 2 + 1}.</span>`);
      for (const j of [i, i + 1]) {
        if (j >= jogo.san.length) { partes.push("<span></span>"); continue; }
        const cl = temAnalise() ? jogo.cl[j] : "";
        const marca = cl && cl !== "melhor" ? `<span class="lance__marca cl-${cl}" title="${NOME_CLASSE[cl]}">${MARCA[cl]}</span>` : "";
        partes.push(`<button type="button" class="lance" data-ply="${j + 1}">${esc(jogo.san[j])}${marca}</button>`);
      }
    }
    el.innerHTML = partes.join("");
  }

  function marcarLanceAtual() {
    const el = $("vis-lances");
    el.querySelectorAll(".lance--atual").forEach((b) => b.classList.remove("lance--atual"));
    const atual = el.querySelector(`[data-ply="${ply}"]`);
    if (atual) {
      atual.classList.add("lance--atual");
      const topo = atual.offsetTop - el.offsetTop;
      if (topo < el.scrollTop || topo > el.scrollTop + el.clientHeight - 30) el.scrollTop = topo - el.clientHeight / 2;
    } else if (!ply) el.scrollTop = 0;
  }

  function renderResumo() {
    const el = $("vis-resumo");
    const r = jogo.res;
    const linhasChessCom = partida.precisao != null
      ? `<tr><td>Precisão (Chess.com)</td><td class="num">${partida.precisao.toFixed(1).replace(".", ",")}</td><td class="num">${partida.precisao_adv != null ? partida.precisao_adv.toFixed(1).replace(".", ",") : "—"}</td></tr>` : "";
    if (!r) {
      el.innerHTML = linhasChessCom ? `<table><thead><tr><th></th><th class="num">Você</th><th class="num">Adversário</th></tr></thead><tbody>${linhasChessCom}</tbody></table>` : "";
      return;
    }
    const f = (x) => (x == null ? "—" : String(x).replace(".", ","));
    el.innerHTML = `<table><thead><tr><th>Motor (Stockfish)</th><th class="num">Você</th><th class="num">Adversário</th></tr></thead><tbody>
      <tr><td>Precisão estimada</td><td class="num">${f(r.precisao)}</td><td class="num">${f(r.precisao_adv)}</td></tr>
      ${linhasChessCom}
      <tr><td><span class="cl-imprecisao">?!</span> Imprecisões</td><td class="num">${r.meus.imprecisao}</td><td class="num">${r.adv.imprecisao}</td></tr>
      <tr><td><span class="cl-erro">?</span> Erros</td><td class="num">${r.meus.erro}</td><td class="num">${r.adv.erro}</td></tr>
      <tr><td><span class="cl-erro_grave">??</span> Erros graves</td><td class="num">${r.meus.erro_grave}</td><td class="num">${r.adv.erro_grave}</td></tr>
      </tbody></table>${r.lance_decisivo != null ? `<button type="button" class="botao botao--peq" style="margin-top:8px" data-ir="${r.lance_decisivo + 1}">Ir para o seu lance decisivo (${numeroLance(r.lance_decisivo)} ${esc(jogo.san[r.lance_decisivo])})</button>` : ""}`;
  }

  // Linha vertical no lance atual
  const pluginCursor = {
    id: "cursorLance",
    afterDatasetsDraw(chart) {
      const x = chart.scales.x.getPixelForValue(ply);
      const { top, bottom } = chart.chartArea;
      const c = chart.ctx;
      c.save(); c.strokeStyle = css("--texto-suave"); c.lineWidth = 1;
      c.beginPath(); c.moveTo(x, top); c.lineTo(x, bottom); c.stroke(); c.restore();
    },
  };

  function renderGrafico() {
    if (grafico) { grafico.destroy(); grafico = null; }
    const eu = minhaCor();
    const n = jogo.san.length;
    const xs = Array.from({ length: n + 1 }, (_, i) => i);
    let dados, rotulo, yCfg, base, nota;
    if (temAnalise()) {
      dados = jogo.av.map((v) => (eu === "white" ? chance(v) : 100 - chance(v)));
      rotulo = "Sua chance de vitória";
      yCfg = { min: 0, max: 100, ticks: { callback: (v) => v + "%", stepSize: 50 } };
      base = 50;
      nota = "Sua chance de vitória segundo o motor, lance a lance. Pontos marcam seus erros; clique para ir ao lance.";
    } else {
      dados = [0, ...jogo.sal];
      rotulo = "Saldo de material";
      const lim = Math.max(3, ...dados.map(Math.abs));
      yCfg = { min: -lim, max: lim, ticks: { stepSize: Math.max(1, Math.round(lim / 3)) } };
      base = 0;
      nota = "Saldo de material (seu ponto de vista: peão 1, cavalo/bispo 3, torre 5, dama 9). Clique para ir ao lance.";
    }
    $("vis-nota-grafico").textContent = nota;
    const corVit = css("--vitoria"), corDer = css("--derrota");
    const minhaParidade = eu === "white" ? 0 : 1;
    const raio = xs.map((i) => {
      if (!temAnalise() || !i || (i - 1) % 2 !== minhaParidade) return 0;
      const cl = jogo.cl[i - 1];
      return cl === "erro_grave" ? 5 : cl === "erro" ? 4 : 0;
    });
    grafico = new Chart($("g-vis"), {
      type: "line",
      data: {
        labels: xs,
        datasets: [{
          label: rotulo, data: dados, borderColor: css("--texto-suave"), borderWidth: 1.5, tension: 0.2,
          pointRadius: raio, pointBackgroundColor: corDer, pointBorderColor: css("--superficie"), pointBorderWidth: 2, pointHoverRadius: 4,
          fill: { target: { value: base }, above: corVit + "55", below: corDer + "55" },
        }],
      },
      options: {
        maintainAspectRatio: false, animation: false,
        interaction: { mode: "index", intersect: false },
        scales: { x: { type: "linear", min: 0, max: n, display: false }, y: { ...yCfg, grid: { color: css("--borda") }, border: { display: false } } },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (it) => { const i = it[0].parsed.x; return i ? `${numeroLance(i - 1)} ${jogo.san[i - 1]}` : "Posição inicial"; },
              label: (it) => (temAnalise() ? ` ${rotulo}: ${Math.round(it.raw)}% (${fmtAval(jogo.av[it.parsed.x])})` : ` ${rotulo}: ${it.raw > 0 ? "+" : ""}${it.raw}`),
            },
          },
        },
        onClick: (ev, _els, chart) => {
          const x = chart.scales.x.getValueForPixel(ev.x);
          irPara(Math.round(x));
        },
      },
      plugins: [pluginCursor],
    });
  }

  // Meios-lances (1..n) em que eu cometi erro ou erro grave
  function meusErros() {
    if (!temAnalise()) return [];
    const par = minhaCor() === "white" ? 0 : 1;
    return jogo.cl.map((c, i) => (i % 2 === par && (c === "erro" || c === "erro_grave") ? i + 1 : null)).filter((x) => x != null);
  }

  function irPara(k) {
    ply = Math.max(0, Math.min(jogo.san.length, k));
    if (partida) history.replaceState(null, "", `#partida=${partida.uuid}${ply ? `&lance=${ply}` : ""}`);
    renderTabuleiro();
    renderJogadores();
    renderComentario();
    marcarLanceAtual();
    if (grafico) grafico.draw();
  }

  // ---------- Abrir / fechar ----------
  async function abrir(p, lanceInicial = 0) {
    partida = p;
    const dlg = $("visualizador");
    const app = window.ChessApp;
    $("vis-titulo").innerHTML = `${p.cor === "brancas" ? "Brancas" : "Pretas"} contra ${esc(p.adversario)} — <span class="badge badge--${p.resultado}">${RES_TEXTO[p.resultado]}</span>`;
    $("vis-sub").textContent = `${app.fmtData(p.data)} ${String(p.hora).padStart(2, "0")}h · ${app.NOME_RITMO[p.ritmo] || p.ritmo} ${app.fmtControle(p.controle)} · ${p.abertura || "abertura não identificada"} · ${p.lances} lances`;
    $("vis-link").href = p.url;
    $("vis-comentario").textContent = "Carregando…";
    $("vis-lances").innerHTML = ""; $("vis-resumo").innerHTML = "";
    if (!dlg.open) dlg.showModal();
    history.replaceState(null, "", `#partida=${p.uuid}`);
    try {
      const [mes] = await Promise.all([carregarMes(p.mes), carregarChessground()]);
      if (partida !== p) return;   // outra partida foi aberta enquanto carregava
      jogo = mes[p.uuid];
      if (!jogo) throw new Error("Partida sem lances registrados.");
    } catch (e) {
      console.error(e);
      $("vis-comentario").textContent = `Não foi possível carregar a partida: ${e.message || e}`;
      return;
    }
    orientacao = minhaCor();
    if (!cg) {
      cg = Chessground($("vis-tabuleiro"), {
        viewOnly: true, coordinates: true, fen: jogo.fi, orientation: orientacao,
        animation: { enabled: true, duration: 160 },
        drawable: { enabled: false, visible: true },
      });
    }
    renderLances();
    renderResumo();
    $("vis-nav-erros").hidden = !meusErros().length;
    renderGrafico();
    irPara(lanceInicial);
    dlg.focus();
    requestAnimationFrame(() => cg.redrawAll());
  }

  function fechar() {
    const dlg = $("visualizador");
    if (dlg.open) dlg.close();
  }

  function iniciar() {
    const dlg = $("visualizador");
    $("vis-fechar").addEventListener("click", fechar);
    dlg.addEventListener("close", () => {
      if (location.hash.startsWith("#partida=")) history.replaceState(null, "", location.pathname + location.search);
      partida = null;
    });
    dlg.addEventListener("click", (ev) => { if (ev.target === dlg) fechar(); });   // clique no fundo
    dlg.addEventListener("keydown", (ev) => {
      if (!jogo || ev.target.closest("input")) return;
      const acoes = { ArrowLeft: () => irPara(ply - 1), ArrowRight: () => irPara(ply + 1), Home: () => irPara(0), End: () => irPara(jogo.san.length), ArrowUp: () => irPara(0), ArrowDown: () => irPara(jogo.san.length) };
      if (acoes[ev.key]) { ev.preventDefault(); acoes[ev.key](); }
      else if (ev.key === "f") { orientacao = orientacao === "white" ? "black" : "white"; irPara(ply); }
    });
    dlg.querySelector(".vis__esq").addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-nav]");
      if (!b || !jogo) return;
      ({ inicio: () => irPara(0), ant: () => irPara(ply - 1), prox: () => irPara(ply + 1), fim: () => irPara(jogo.san.length),
         virar: () => { orientacao = orientacao === "white" ? "black" : "white"; irPara(ply); },
         "erro-prox": () => { const e = meusErros().find((x) => x > ply); if (e) irPara(e); },
         "erro-ant": () => { const e = meusErros().filter((x) => x < ply).pop(); if (e) irPara(e); } })[b.dataset.nav]();
    });
    $("vis-lances").addEventListener("click", (ev) => { const b = ev.target.closest("[data-ply]"); if (b) irPara(+b.dataset.ply); });
    $("vis-resumo").addEventListener("click", (ev) => { const b = ev.target.closest("[data-ir]"); if (b) irPara(+b.dataset.ir); });
    window.addEventListener("resize", () => cg && cg.redrawAll());
  }

  window.Visualizador = { abrir, iniciar, redesenhar: () => { if (jogo && partida) { renderGrafico(); } } };
})();
