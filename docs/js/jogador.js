/* ===== Chess Tracking — jogador selecionado =====
   Lê docs/dados/jogadores.json, resolve o jogador da URL (?j=<usuario>; sem ele,
   o primeiro da lista), monta o seletor no cabeçalho e mantém o ?j= nas abas.
   As outras páginas esperam `Jogador.pronto` e buscam dados em `Jogador.base`. */
(function () {
  "use strict";

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const Jogador = { usuario: null, nome: null, base: null, lista: [] };

  // Mesmo endereço, trocando só o jogador (o #partida=… / #posição é de um jogador só, então sai)
  const urlDe = (usuario, pagina) => `${pagina ?? location.pathname}?j=${encodeURIComponent(usuario)}`;

  function montarSeletor() {
    const el = document.getElementById("jogadores");
    if (!el || Jogador.lista.length < 2) return;
    el.innerHTML = Jogador.lista.map((j) => {
      const atual = j.usuario === Jogador.usuario;
      const ini = esc(j.nome.slice(0, 1).toUpperCase());
      const foto = j.avatar
        ? `<img src="${esc(j.avatar)}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'jogador__ini',textContent:'${ini}'}))">`
        : `<span class="jogador__ini">${ini}</span>`;
      return `<a class="jogador" href="${esc(urlDe(j.usuario))}"${atual ? ' aria-current="true"' : ""}>${foto}<span>${esc(j.nome)}</span></a>`;
    }).join("");
    el.hidden = false;
  }

  function ajustarAbas() {
    document.querySelectorAll(".abas .aba").forEach((a) => {
      const destino = a.getAttribute("href").split("?")[0];
      a.setAttribute("href", urlDe(Jogador.usuario, destino));
    });
  }

  Jogador.link = (pagina) => urlDe(Jogador.usuario, pagina);

  Jogador.pronto = fetch("dados/jogadores.json", { cache: "no-cache" })
    .then((r) => { if (!r.ok) throw new Error(`dados/jogadores.json: HTTP ${r.status}`); return r.json(); })
    .then((idx) => {
      Jogador.lista = idx.jogadores || [];
      if (!Jogador.lista.length) throw new Error("Nenhum jogador publicado");
      const pedido = (new URLSearchParams(location.search).get("j") || "").toLowerCase();
      const j = Jogador.lista.find((x) => x.usuario === pedido) || Jogador.lista[0];
      Object.assign(Jogador, { usuario: j.usuario, nome: j.nome, base: `dados/${encodeURIComponent(j.usuario)}/` });
      // Links antigos sem ?j= (ou com um jogador que saiu) continuam valendo
      if (pedido !== j.usuario) history.replaceState(null, "", urlDe(j.usuario) + location.hash);
      montarSeletor();
      ajustarAbas();
      return Jogador;
    });

  window.Jogador = Jogador;
})();
