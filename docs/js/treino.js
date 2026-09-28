/* ===== Chess Tracking — treino dos erros graves =====
   Lê docs/dados/<usuario>/treino.json (gerado pela publicação): posições logo antes
   de cada erro grave do jogador, com lances legais, melhor lance e alternativas aceitas.
   O progresso fica no localStorage deste navegador, separado por jogador. */
(function () {
  "use strict";

  const CG_BASE = "https://cdn.jsdelivr.net/npm/@lichess-org/chessground@10.4.0";
  const MAX_TENTATIVAS = 3;
  const CHAVE_PROGRESSO_ANTIGA = "treino-progresso-v1";   // de quando só havia o giggsmate
  let CHAVE_PROGRESSO = CHAVE_PROGRESSO_ANTIGA;
  const NOME_RITMO = { bullet: "Bullet", blitz: "Blitz", rapid: "Rapid", daily: "Daily" };
  const NOME_FASE = { abertura: "Abertura (lances 1–10)", meio: "Meio-jogo (11–25)", final: "Final (26+)" };
  const RITMOS = ["bullet", "blitz", "rapid", "daily"];

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtData = (iso) => iso.split("-").reverse().join("/");
  function fmtControle(ctrl) {
    if (!ctrl) return "";
    if (ctrl.includes("/")) return "1 dia/lance";
    const [b, inc] = ctrl.split("+").map(Number);
    return (b >= 60 ? `${b / 60} min` : `${b}s`) + (inc ? ` + ${inc}s` : "");
  }

  // ---------- Estado ----------
  const estado = { ritmo: "todos", fase: "todas", modo: "aleatorio" };
  let TODAS = [], fila = [], indice = 0, pos = null;
  let tentativas = 0, usouDica = false, terminou = false;
  let cg = null, Chessground = null;
  const sessao = { certas: 0, feitas: 0, sequencia: 0 };

  function lerProgresso() {
    try {
      let bruto = localStorage.getItem(CHAVE_PROGRESSO);
      if (bruto == null && Jogador.usuario === "giggsmate") {
        bruto = localStorage.getItem(CHAVE_PROGRESSO_ANTIGA);
        if (bruto != null) { localStorage.setItem(CHAVE_PROGRESSO, bruto); localStorage.removeItem(CHAVE_PROGRESSO_ANTIGA); }
      }
      return JSON.parse(bruto || "{}");
    } catch (e) { return {}; }
  }
  let progresso = {};
  function registrar(id, ok) {
    const r = progresso[id] || { ok: 0, erro: 0 };
    r[ok ? "ok" : "erro"]++;
    r.ult = ok ? "ok" : "erro";
    progresso[id] = r;
    try { localStorage.setItem(CHAVE_PROGRESSO, JSON.stringify(progresso)); } catch (e) { /* armazenamento indisponível */ }
  }

  // ---------- Fila ----------
  function embaralhar(a) {
    for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
    return a;
  }
  function filtradas() {
    return TODAS.filter((p) => (estado.ritmo === "todos" || p.ritmo === estado.ritmo) && (estado.fase === "todas" || p.fase === estado.fase));
  }
  function montarFila() {
    const base = filtradas();
    if (estado.modo === "recentes") fila = base.slice();
    else if (estado.modo === "erradas") fila = base.filter((p) => progresso[p.id] && progresso[p.id].ult === "erro");
    else {
      // Aleatória, com as posições nunca vistas primeiro
      const novas = embaralhar(base.filter((p) => !progresso[p.id]));
      const vistas = embaralhar(base.filter((p) => progresso[p.id]));
      fila = novas.concat(vistas);
    }
    indice = 0;
    renderPlacar();
    if (fila.length) mostrar(fila[0]);
    else semPosicoes();
  }

  // ---------- Tabuleiro ----------
  function mapaDests(d) {
    const m = new Map();
    for (const [orig, destinos] of Object.entries(d)) m.set(orig, destinos.match(/../g));
    return m;
  }
  const quadrados = (uci) => [uci.slice(0, 2), uci.slice(2, 4)];
  const nomeCor = (c) => (c === "white" ? "brancas" : "pretas");

  function prepararPosicao(travado) {
    cg.set({
      fen: pos.fen, orientation: pos.cor, turnColor: pos.cor,
      lastMove: pos.ult ? quadrados(pos.ult) : undefined,
      check: pos.xeque ? pos.cor : false,
      selected: undefined,
      movable: { free: false, color: travado ? undefined : pos.cor, dests: mapaDests(pos.dests), showDests: true, events: { after: aoMover } },
      drawable: { autoShapes: usouDica ? [{ orig: pos.melhor_uci.slice(0, 2), brush: "green" }] : [] },
    });
  }

  function mostrar(p) {
    pos = p; tentativas = 0; usouDica = false; terminou = false;
    prepararPosicao(false);
    $("t-vez").innerHTML = `<span class="peca peca--${nomeCor(p.cor)}"></span>Você joga de <strong>${nomeCor(p.cor)}</strong> — encontre o melhor lance`;
    const prog = progresso[p.id];
    $("t-contexto").innerHTML = `
      <div class="treino__meta"><span class="ponto" style="background:var(--${p.ritmo})"></span>${NOME_RITMO[p.ritmo] || p.ritmo} ${esc(fmtControle(p.controle))}
        · ${fmtData(p.data)} · lance ${esc(p.num)} · ${esc(NOME_FASE[p.fase])}</div>
      <div>contra <strong>${esc(p.adversario)}</strong> (${p.adv_rating ?? "—"}) · ${esc(p.abertura || "abertura não identificada")}</div>
      <div class="treino__chance">Antes do lance, sua chance de vitória era <strong>${p.chance_antes}%</strong> (${esc(p.antes)}).</div>
      ${prog ? `<div class="treino__historico">Você já viu esta posição: ${prog.ok} acerto(s), ${prog.erro} erro(s).</div>` : ""}`;
    status("", "");
    $("t-link-partida").href = `${Jogador.link("./")}#partida=${p.uuid}&lance=${p.ply}`;
    $("t-dica").disabled = false;
    $("t-solucao").disabled = false;
    renderPlacar();
  }

  function semPosicoes() {
    pos = null;
    cg.set({ fen: "8/8/8/8/8/8/8/8", lastMove: undefined, check: false, movable: { color: undefined }, drawable: { autoShapes: [] } });
    $("t-vez").textContent = "";
    $("t-contexto").innerHTML = estado.modo === "erradas"
      ? "Nenhuma posição para revisar neste filtro — você ainda não errou nenhuma (ou já acertou todas na revisão)."
      : "Nenhuma posição neste filtro.";
    status("", "");
    $("t-dica").disabled = true; $("t-solucao").disabled = true;
  }

  function status(html, tipo) {
    const el = $("t-status");
    el.className = "treino__status" + (tipo ? ` treino__status--${tipo}` : "");
    el.innerHTML = html;
  }

  function revelacaoPartida() {
    return `<div class="treino__partida">Na partida você jogou <strong>${esc(pos.num)} ${esc(pos.jogado)}??</strong> — sua chance caiu de ${pos.chance_antes}% para ${pos.chance_depois}% (${esc(pos.antes)} → ${esc(pos.depois)}).</div>`;
  }
  function linhaMotor() {
    return pos.linha && pos.linha.length ? `<div class="treino__linha">Linha do motor: ${esc(pos.linha.join(" "))}</div>` : "";
  }

  function finalizar(acertou, lanceAceito) {
    terminou = true;
    const valeu = acertou && tentativas === 0 && !usouDica;
    registrar(pos.id, valeu);
    sessao.feitas++;
    if (valeu) { sessao.certas++; sessao.sequencia++; } else sessao.sequencia = 0;
    const setaMelhor = { orig: pos.melhor_uci.slice(0, 2), dest: pos.melhor_uci.slice(2, 4), brush: "green" };
    if (!acertou || lanceAceito === pos.melhor_uci) {
      cg.set({ fen: pos.fen_sol, lastMove: quadrados(pos.melhor_uci), check: false, movable: { color: undefined }, drawable: { autoShapes: [setaMelhor] } });
    } else {
      cg.set({ movable: { color: undefined }, drawable: { autoShapes: [setaMelhor] } });
    }
    $("t-dica").disabled = true; $("t-solucao").disabled = true;
    renderPlacar();
  }

  function aoMover(orig, dest) {
    if (terminou || !pos) return;
    let uci = orig + dest;
    const peca = cg.state.pieces.get(dest);
    if (peca && peca.role === "pawn" && (dest[1] === "8" || dest[1] === "1")) {
      uci += "q";
      cg.setPieces(new Map([[dest, { role: "queen", color: peca.color, promoted: true }]]));
    }
    const aceito = pos.aceitos.find((a) => a === uci || (a.length === 5 && a.slice(0, 4) === uci.slice(0, 4)));
    if (aceito) {
      const iAceito = pos.aceitos.indexOf(aceito);
      const san = pos.aceitos_san[iAceito];
      const extra = aceito === pos.melhor_uci ? "" : `<div>Também serve! O melhor segundo o motor era <strong>${esc(pos.melhor)}</strong>.</div>`;
      const aviso = tentativas || usouDica ? `<div class="treino__obs">Conta como revisão${usouDica ? " (usou dica)" : ""}${tentativas ? ` (${tentativas + 1}ª tentativa)` : ""} — ela volta em "Revisar erradas".</div>` : "";
      status(`<strong>✓ Correto: ${esc(san)}</strong>${extra}${linhaMotor()}${revelacaoPartida()}${aviso}`, "ok");
      finalizar(true, aceito);
      return;
    }
    tentativas++;
    const eraOErro = uci.slice(0, 4) === pos.jogado_uci.slice(0, 4);
    if (tentativas >= MAX_TENTATIVAS) {
      status(`<strong>✗ ${eraOErro ? "Esse foi o lance da partida." : "Não era esse."}</strong> A solução era <strong>${esc(pos.melhor)}</strong>.${linhaMotor()}${revelacaoPartida()}`, "erro");
      finalizar(false);
      return;
    }
    const restam = MAX_TENTATIVAS - tentativas;
    status(`<strong>${eraOErro ? "Esse foi exatamente o erro da partida." : "Não é o melhor lance."}</strong> Tente de novo — ${restam} tentativa${restam > 1 ? "s" : ""} restante${restam > 1 ? "s" : ""}.`, "aviso");
    cg.set({ movable: { color: undefined } });
    setTimeout(() => { if (!terminou && pos) prepararPosicao(false); }, 700);
  }

  function dica() {
    if (!pos || terminou) return;
    usouDica = true;
    cg.set({ drawable: { autoShapes: [{ orig: pos.melhor_uci.slice(0, 2), brush: "green" }] } });
    status("💡 Mova a peça destacada.", "aviso");
  }
  function solucao() {
    if (!pos || terminou) return;
    status(`A solução é <strong>${esc(pos.melhor)}</strong>.${linhaMotor()}${revelacaoPartida()}`, "erro");
    finalizar(false);
  }
  function proxima() {
    if (!fila.length) return;
    indice++;
    if (indice >= fila.length) {
      status(`<strong>Fim da fila!</strong> Você passou pelas ${fila.length} posições deste filtro. Uma nova rodada começou.`, "ok");
      montarFila();
      return;
    }
    mostrar(fila[indice]);
  }

  // ---------- Placar ----------
  function renderPlacar() {
    const base = filtradas();
    const vistas = base.filter((p) => progresso[p.id]);
    const certas = base.filter((p) => progresso[p.id] && progresso[p.id].ult === "ok").length;
    const revisar = base.filter((p) => progresso[p.id] && progresso[p.id].ult === "erro").length;
    $("t-resumo").textContent = `${base.length} posições no filtro · posição ${fila.length ? Math.min(indice + 1, fila.length) : 0} de ${fila.length}`;
    $("t-placar").innerHTML = `
      <div class="kpi"><div class="kpi__rotulo">Nesta sessão</div><div class="kpi__valor">${sessao.certas} / ${sessao.feitas}</div><div class="kpi__extra">certas de primeira · sequência ${sessao.sequencia}</div></div>
      <div class="kpi"><div class="kpi__rotulo">Neste filtro</div><div class="kpi__valor">${certas} / ${base.length}</div><div class="kpi__extra">resolvidas · ${vistas.length} já vistas</div></div>
      <div class="kpi"><div class="kpi__rotulo">Para revisar</div><div class="kpi__valor">${revisar}</div><div class="kpi__extra">erradas na última tentativa</div></div>`;
  }

  // ---------- Filtros ----------
  function montarChips(id, opcoes, chave) {
    const el = $(id);
    el.innerHTML = opcoes.map((o) => `<button type="button" class="chip" data-v="${o.chave}" aria-pressed="${estado[chave] === o.chave}">${o.ponto ? `<span class="ponto" style="background:var(--${o.chave})"></span>` : ""}${esc(o.nome)}${o.n != null ? ` <span class="chip__n">${o.n}</span>` : ""}</button>`).join("");
    el.addEventListener("click", (ev) => {
      const b = ev.target.closest(".chip");
      if (!b) return;
      estado[chave] = b.dataset.v;
      el.querySelectorAll(".chip").forEach((x) => x.setAttribute("aria-pressed", x.dataset.v === estado[chave]));
      montarFila();
    });
  }

  // ---------- Tema ----------
  function iniciarTema() {
    const botoes = document.querySelectorAll("#tema-switch .tema-switch__btn");
    const escuro = window.matchMedia("(prefers-color-scheme: dark)");
    const atual = () => document.documentElement.getAttribute("data-theme") || (escuro.matches ? "dark" : "light");
    const marcar = () => botoes.forEach((b) => b.setAttribute("aria-pressed", b.dataset.tema === atual()));
    botoes.forEach((b) => b.addEventListener("click", () => {
      document.documentElement.setAttribute("data-theme", b.dataset.tema);
      try { localStorage.setItem("tema", b.dataset.tema); } catch (e) { /* armazenamento indisponível */ }
      marcar();
    }));
    escuro.addEventListener("change", marcar);
    marcar();
  }

  // ---------- Início ----------
  async function iniciar() {
    iniciarTema();
    await Jogador.pronto;
    CHAVE_PROGRESSO = `treino-progresso-v1:${Jogador.usuario}`;
    progresso = lerProgresso();
    $("t-titulo").textContent = `Treino dos erros graves de ${Jogador.nome}`;
    document.title = `Treino de ${Jogador.nome} — Chess Tracking`;
    // O CSS do chessground precisa estar aplicado antes de criar o tabuleiro: ele mede
    // o tamanho das casas na criação, e medidas erradas fazem o primeiro clique se perder.
    const css = ["chessground.base.css", "chessground.brown.css", "chessground.cburnett.css"].map((f) => new Promise((ok) => {
      const l = document.createElement("link"); l.rel = "stylesheet"; l.href = `${CG_BASE}/assets/${f}`;
      l.onload = l.onerror = ok; document.head.appendChild(l);
    }));
    const [dados, mod] = (await Promise.all([
      ...css,
      fetch(`${Jogador.base}treino.json`, { cache: "no-cache" }).then((r) => { if (!r.ok) throw new Error(`${Jogador.base}treino.json: HTTP ${r.status}`); return r.json(); }),
      import(`${CG_BASE}/dist/chessground.min.js`),
    ])).slice(-2);
    Chessground = mod.Chessground;
    TODAS = dados.posicoes || [];
    cg = Chessground($("t-tabuleiro"), {
      coordinates: true, animation: { enabled: true, duration: 180 },
      premovable: { enabled: false }, draggable: { showGhost: true },
      drawable: { enabled: false, visible: true },
    });
    const conta = (f) => TODAS.filter(f).length;
    $("meta-treino").textContent = TODAS.length
      ? `${TODAS.length} posições das partidas de ${Jogador.nome} logo antes de um erro grave. Encontre o lance certo.`
      : `Ainda não há posições de treino para ${Jogador.nome}: as partidas entram aqui depois de analisadas pelo Stockfish na atualização diária.`;
    montarChips("t-filtro-ritmo", [{ chave: "todos", nome: "Todos", n: TODAS.length },
      ...RITMOS.filter((r) => conta((p) => p.ritmo === r)).map((r) => ({ chave: r, nome: NOME_RITMO[r], ponto: true, n: conta((p) => p.ritmo === r) }))], "ritmo");
    montarChips("t-filtro-fase", [{ chave: "todas", nome: "Todas" }, { chave: "abertura", nome: "Abertura" }, { chave: "meio", nome: "Meio-jogo" }, { chave: "final", nome: "Final" }], "fase");
    montarChips("t-filtro-modo", [{ chave: "aleatorio", nome: "Aleatória" }, { chave: "recentes", nome: "Mais recentes" }, { chave: "erradas", nome: "Revisar erradas" }], "modo");

    $("t-dica").addEventListener("click", dica);
    $("t-solucao").addEventListener("click", solucao);
    $("t-proxima").addEventListener("click", proxima);
    document.addEventListener("keydown", (ev) => {
      if (ev.target.closest("input, textarea")) return;
      if (ev.key === "ArrowRight" || ev.key === "n" || ev.key === "N") { ev.preventDefault(); proxima(); }
      else if (ev.key === "d" || ev.key === "D") dica();
      else if (ev.key === "s" || ev.key === "S") solucao();
    });
    window.addEventListener("resize", () => cg && cg.redrawAll());
    // Link direto para uma posição: treino.html#<uuid>:<ply>
    const alvo = decodeURIComponent(location.hash.slice(1));
    montarFila();
    if (alvo) { const i = fila.findIndex((p) => p.id === alvo); if (i >= 0) { indice = i; mostrar(fila[i]); } }
  }

  iniciar().catch((e) => {
    console.error(e);
    $("meta-treino").textContent = `Erro ao carregar o treino: ${e.message || e}`;
  });
})();
