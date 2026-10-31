const $ = (sel, el = document) => el.querySelector(sel);

function ligaId() {
  const m = location.pathname.match(/\/liga\/(\d+)/);
  return m ? Number(m[1]) : null;
}

function abaInicial() {
  const q = new URLSearchParams(location.search).get("aba");
  const map = { principal: "classificacao", geral: "classificacao", ultimos: "rodadas" };
  const aba = map[q] || q;
  return ["classificacao", "rodadas", "artilharia", "estatisticas"].includes(aba) ? aba : "classificacao";
}

function n(v, dig = 0) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("pt-BR", {
    minimumFractionDigits: dig,
    maximumFractionDigits: dig,
  });
}

function fmtData(iso) {
  if (!iso) return "";
  const [y, m, d] = String(iso).slice(0, 10).split("-");
  return `${d}/${m}`;
}

function logo(src, size = 20) {
  if (!src) return "";
  return `<img src="${src}" alt="" style="width:${size}px;height:${size}px;object-fit:contain" loading="lazy" decoding="async" onerror="this.style.opacity=.2" />`;
}

function cellEntity(fotoHtml, nome, href = null) {
  const label = nome || "—";
  const text = href ? `<a class="entity-link" href="${href}">${label}</a>` : `<span>${label}</span>`;
  return `<td><div class="cell-inner">${fotoHtml || ""}${text}</div></td>`;
}

function jogosLista(jogos) {
  if (!jogos?.length) return `<div class="empty">Sem jogos.</div>`;
  return jogos
    .map((j) => {
      const feito = j.gols_casa != null && j.gols_fora != null;
      const corpo = `
      <div class="jogo-status">
        ${feito ? `<div class="fj">FT</div>` : ""}
        <div>${fmtData(j.data)}</div>
      </div>
      <div class="times">
        <div class="time">${logo(j.casa_logo)}<span>${j.casa}</span></div>
        <div class="time">${logo(j.fora_logo)}<span>${j.fora}</span></div>
      </div>
      <div class="placar">
        <div>${feito ? j.gols_casa : ""}</div>
        <div>${feito ? j.gols_fora : ""}</div>
      </div>`;
      // Futuros: só o confronto (sem link de detalhe / sem placar).
      if (!feito) return `<div class="jogo-row jogo-row-futuro">${corpo}</div>`;
      return `<a class="jogo-row" href="/jogo/${j.id}">${corpo}</a>`;
    })
    .join("");
}

function indexRodadaInicial(rodadas, destaque) {
  if (!rodadas?.length) return 0;
  if (destaque != null) {
    const i = rodadas.findIndex((r) => Number(r.n_rodada) === Number(destaque));
    if (i >= 0) return i;
  }
  return rodadas.length - 1;
}

function rodadasNavHtml(rodadas, idx) {
  if (!rodadas?.length) return `<div class="empty">Sem rodadas.</div>`;
  const r = rodadas[idx];
  const prevDis = idx <= 0 ? "disabled" : "";
  const nextDis = idx >= rodadas.length - 1 ? "disabled" : "";
  return `
    <div class="rodadas-nav">
      <button type="button" class="rodada-btn" id="rodada-prev" aria-label="Rodada anterior" ${prevDis}>‹</button>
      <select id="rodada-select" class="rodada-select" aria-label="Selecionar rodada">
        ${rodadas
          .map(
            (x, i) =>
              `<option value="${i}" ${i === idx ? "selected" : ""}>${x.rodada || `Rodada ${x.n_rodada}`}</option>`
          )
          .join("")}
      </select>
      <button type="button" class="rodada-btn" id="rodada-next" aria-label="Próxima rodada" ${nextDis}>›</button>
    </div>
    <article class="liga-block" id="rodada-panel" style="margin:0">
      ${jogosLista(r.jogos)}
    </article>`;
}

function bindRodadasNav(rodadas) {
  const prev = $("#rodada-prev");
  const next = $("#rodada-next");
  const sel = $("#rodada-select");
  const panel = $("#rodada-panel");
  if (!sel || !panel || !rodadas?.length) return;

  function go(i) {
    const idx = Math.max(0, Math.min(rodadas.length - 1, i));
    state.rodadaIdx = idx;
    sel.value = String(idx);
    if (prev) prev.disabled = idx <= 0;
    if (next) next.disabled = idx >= rodadas.length - 1;
    panel.innerHTML = jogosLista(rodadas[idx].jogos);
  }

  prev?.addEventListener("click", () => go(state.rodadaIdx - 1));
  next?.addEventListener("click", () => go(state.rodadaIdx + 1));
  sel.addEventListener("change", () => go(Number(sel.value)));
}

let classifSort = { key: "pts", ordem: "desc" };

function tabelaClassificacao(rows) {
  if (!rows?.length) return `<div class="empty">Sem classificação.</div>`;
  const list = [...rows];
  const rev = classifSort.ordem === "desc";
  const key = classifSort.key;
  list.forEach(r => { const j=Number(r.j||0);r.aproveitamento=j>0?100*(3*Number(r.v||0)+Number(r.e||0))/(3*j):null; });
  list.sort((a, b) => {
    if (key === "clube") {
      const va = (a.clube || "").toLowerCase();
      const vb = (b.clube || "").toLowerCase();
      if (va < vb) return rev ? 1 : -1;
      if (va > vb) return rev ? -1 : 1;
      return 0;
    }
    const va = Number(a[key] ?? -Infinity);
    const vb = Number(b[key] ?? -Infinity);
    return rev ? vb - va : va - vb;
  });
  const mark = (k) => (classifSort.key === k ? (classifSort.ordem === "desc" ? " ↓" : " ↑") : "");
  const th = (k, lab) => `<th class="sortable" data-csort="${k}">${lab}${mark(k)}</th>`;
  return `
    <div class="table-wrap">
      <table class="data-table" id="tbl-classif">
        <thead>
          <tr>
            <th>#</th>${th("clube", "Clube")}${th("pts", "Pts")}${th("j", "J")}${th("v", "V")}${th("e", "E")}${th("d", "D")}
            ${th("gp", "GP")}${th("gc", "GC")}${th("sg", "SG")}${th("aproveitamento", "Aprov. %")}
            ${th("clean_sheets", "CS")}${th("clean_goals", "CG")}
          </tr>
        </thead>
        <tbody>
          ${list
            .map(
              (r, i) => `<tr>
              <td>${i + 1}</td>
              ${cellEntity(logo(r.logo, 18), r.clube, r.clube_id ? `/clube/${r.clube_id}` : null)}
              <td><strong>${r.pts}</strong></td>
              <td>${r.j}</td><td>${r.v}</td><td>${r.e}</td><td>${r.d}</td>
              <td>${r.gp}</td><td>${r.gc}</td><td>${r.sg}</td><td>${r.aproveitamento == null ? "—" : r.aproveitamento.toLocaleString("pt-BR", {minimumFractionDigits:1,maximumFractionDigits:1}) + "%"}</td>
              <td title="Clean sheets">${r.clean_sheets ?? 0}</td>
              <td title="Clean goals">${r.clean_goals ?? 0}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
}

let state = {
  dados: null,
  aba: abaInicial(),
  rodadaIdx: 0,
  art: {
    posicao: "",
    clube_id: "",
    nacionalidade: "",
    sort: "gols",
    ordem: "desc",
  },
  stats: {
    grupo: "ataque",
    selecionados: [],
    modo: "soma",
    sort: null,
    ordem: "desc",
    data: null,
    grupos: null,
  },
};

function sortIcon(key) {
  if (state.art.sort !== key) return "";
  return state.art.ordem === "desc" ? " ↓" : " ↑";
}

function filtrarArtilharia(rows) {
  const f = state.art;
  let out = [...(rows || [])];
  if (f.posicao) out = out.filter((r) => r.posicao === f.posicao);
  if (f.clube_id) out = out.filter((r) => String(r.clube_id) === String(f.clube_id));
  if (f.nacionalidade) out = out.filter((r) => r.nacionalidade === f.nacionalidade);

  const key = f.sort;
  const rev = f.ordem === "desc";
  out.sort((a, b) => {
    let va = a[key];
    let vb = b[key];
    if (key === "nome" || key === "clube" || key === "posicao" || key === "nacionalidade") {
      va = (va || "").toString().toLowerCase();
      vb = (vb || "").toString().toLowerCase();
      if (va < vb) return rev ? 1 : -1;
      if (va > vb) return rev ? -1 : 1;
      return 0;
    }
    va = Number(va ?? -Infinity);
    vb = Number(vb ?? -Infinity);
    return rev ? vb - va : va - vb;
  });
  return out;
}

function tabelaArtilharia(rows, filtros) {
  const list = filtrarArtilharia(rows);
  const th = (key, label) =>
    `<th class="sortable" data-sort="${key}">${label}${sortIcon(key)}</th>`;

  return `
    <div class="filters-row">
      <label>Posição
        <select id="art-pos">
          <option value="">Todas</option>
          ${(filtros?.posicoes || []).map((p) => `<option value="${p}" ${state.art.posicao === p ? "selected" : ""}>${p}</option>`).join("")}
        </select>
      </label>
      <label>Clube
        <select id="art-clube">
          <option value="">Todos</option>
          ${(filtros?.clubes || []).map((c) => `<option value="${c.id}" ${String(state.art.clube_id) === String(c.id) ? "selected" : ""}>${c.clube}</option>`).join("")}
        </select>
      </label>
      <label>Nacionalidade
        <select id="art-nac">
          <option value="">Todas</option>
          ${(filtros?.nacionalidades || []).map((p) => `<option value="${p}" ${state.art.nacionalidade === p ? "selected" : ""}>${p}</option>`).join("")}
        </select>
      </label>
    </div>
    <div class="table-wrap">
      <table class="data-table player-table" id="tbl-art">
        <thead>
          <tr>
            <th>#</th>
            ${th("nome", "Jogador")}
            ${th("clube", "Clube")}
            ${th("posicao", "Posição")}
            ${th("nacionalidade", "Nacionalidade")}
            ${th("gols", "Gols")}
            ${th("assistencias", "Assists")}
            ${th("jogos", "Jogos")}
            ${th("rating_medio", "Nota")}
          </tr>
        </thead>
        <tbody>
          ${
            list.length
              ? list
                  .map(
                    (r, i) => `<tr>
              <td>${i + 1}</td>
              ${cellEntity(r.foto ? `<img src="${r.foto}" class="mini-av" alt="" loading="lazy" />` : "", r.nome, r.jogador_id || r.id ? `/jogador/${r.jogador_id || r.id}` : null)}
              ${cellEntity(logo(r.clube_logo, 18), r.clube, r.clube_id ? `/clube/${r.clube_id}` : null)}
              <td>${r.posicao || "—"}</td>
              <td>${r.nacionalidade || "—"}</td>
              <td><strong>${r.gols}</strong></td>
              <td>${r.assistencias}</td>
              <td>${r.jogos}</td>
              <td>${n(r.rating_medio, 2)}</td>
            </tr>`
                  )
                  .join("")
              : `<tr><td colspan="9">Sem artilheiros com esses filtros.</td></tr>`
          }
        </tbody>
      </table>
    </div>`;
}

function thSort(key, label, cur, ordem) {
  const mark = cur === key ? (ordem === "desc" ? " ↓" : " ↑") : "";
  return `<th class="sortable" data-sort="${key}">${label}${mark}</th>`;
}

function tabelaColetivas(data, { showCamp = false, modo = "media" } = {}) {
  if (!data?.metricas?.length) return `<div class="empty">Sem dados coletivos.</div>`;
  const mets = data.metricas;
  const dig = (chave, v) => {
    if (v == null) return "—";
    if (chave.includes("posse") || chave === "rating") return n(v, 2);
    return Number.isInteger(Number(v)) ? n(v, 0) : n(v, 2);
  };
  return `
    <div class="table-wrap">
      <table class="data-table stats-table">
        <thead>
          <tr>
            <th>#</th>
            ${thSort("clube", "Clube", data.ordenar, data.ordem)}
            ${showCamp ? thSort("campeonato", "Campeonato", data.ordenar, data.ordem) : ""}
            ${thSort("jogos", "J", data.ordenar, data.ordem)}
            ${mets.map((m) => thSort(m.chave, m.label, data.ordenar, data.ordem)).join("")}
          </tr>
        </thead>
        <tbody>
          ${(data.linhas || [])
            .map((r, i) => {
              const rank = (data.page - 1) * data.page_size + i + 1;
              return `<tr>
              <td>${rank}</td>
              ${cellEntity(logo(r.logo, 18), r.clube, r.clube_id ? `/clube/${r.clube_id}` : null)}
              ${
                showCamp
                  ? `<td><a class="camp-link" href="/liga/${r.campeonato_id}?aba=estatisticas">${r.campeonato || "—"}</a></td>`
                  : ""
              }
              <td>${r.jogos ?? "—"}</td>
              ${mets
                .map((m) => {
                  const v = (r.valores || {})[m.chave] || {};
                  const val = modo === "soma" ? v.soma : v.media;
                  return `<td>${dig(m.chave, val)}</td>`;
                })
                .join("")}
            </tr>`;
            })
            .join("") || `<tr><td colspan="${4 + mets.length}">Sem clubes.</td></tr>`}
        </tbody>
      </table>
    </div>`;
}

function paginacao(data) {
  if (!data || data.pages <= 1) return "";
  return `
    <div class="pager">
      <button type="button" class="pager-btn" data-page="${data.page - 1}" ${data.page <= 1 ? "disabled" : ""}>←</button>
      <span>Página ${data.page} de ${data.pages} · ${data.total} clubes</span>
      <button type="button" class="pager-btn" data-page="${data.page + 1}" ${data.page >= data.pages ? "disabled" : ""}>→</button>
    </div>`;
}

async function loadStatsLiga(page = 1) {
  const d = state.dados;
  if (!d?.id || !d.temporada) return;
  const qs = new URLSearchParams({
    campeonato_id: d.id,
    temporada: d.temporada,
    grupo: state.stats.grupo,
    page: String(page),
    page_size: "20",
    ordem: state.stats.ordem,
  });
  if (state.stats.sort) qs.set("ordenar", state.stats.sort);
  if (state.stats.selecionados.length) {
    qs.set("clubes", state.stats.selecionados.join(","));
  }
  const res = await fetch(`/api/stats/coletivas?${qs.toString().replace(/%2F/gi, "/")}`);
  if (!res.ok) throw new Error("Falha ao carregar estatísticas");
  state.stats.data = await res.json();
  if (state.stats.data.grupos) state.stats.grupos = state.stats.data.grupos;
}

function renderStatsPanel() {
  const clubes = state.dados?.clubes || [];
  const grupos = state.stats.grupos || state.stats.data?.grupos || {
    ataque: "Ataque",
    passes: "Posse e passes",
    defesa: "Defesa",
    duelos: "Duelos e disciplina",
    fisicos: "Dados físicos",
    rating: "Rating",
    finalizacoes: "Finalizações",
  };
  const data = state.stats.data;
  const isFin = state.stats.grupo === "finalizacoes";

  let corpo = "";
  if (isFin) {
    const media = state.stats.modo === "media";
    const val = (r, k) => (media ? r[`${k}_media`] : r[k]);
    corpo = `
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>#</th><th>Clube</th><th>J</th>
              <th>${media ? "Chutes/J" : "Chutes"}</th>
              <th>${media ? "Certas/J" : "Certas"}</th>
              <th>${media ? "Gols/J" : "Gols"}</th>
              <th>Dist. chute</th><th>Dist. certa</th><th>Dist. gol</th>
            </tr>
          </thead>
          <tbody>
            ${(data.linhas || [])
              .map(
                (r, i) => `<tr>
              <td>${(data.page - 1) * data.page_size + i + 1}</td>
              ${cellEntity(logo(r.logo, 18), r.clube, r.clube_id ? `/clube/${r.clube_id}` : null)}
              <td>${r.jogos}</td>
              <td>${n(val(r, "chutes"), media ? 2 : 0)}</td>
              <td>${n(val(r, "certas"), media ? 2 : 0)}</td>
              <td><strong>${n(val(r, "gols"), media ? 2 : 0)}</strong></td>
              <td>${n(r.dist_chute, 1)}</td>
              <td>${n(r.dist_certa, 1)}</td>
              <td>${n(r.dist_gol, 1)}</td>
            </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>
      <p class="fin-hint">Mapa completo de finalizações na página Estatísticas.</p>`;
  } else {
    corpo = `${tabelaColetivas(data, { showCamp: false, modo: state.stats.modo })}
      ${state.stats.selecionados.length ? "" : paginacao(data)}`;
  }

  return `
    <div class="page-heading page-heading-center">
      <h2 class="page-title" style="font-size:clamp(1.6rem,3vw,2rem)">Estatísticas</h2>
    </div>
    <div class="club-picker">
      <div class="club-picker-head">Clubes selecionados (${state.stats.selecionados.length}/5) — deixe vazio para ver todos</div>
      <div class="club-chips">
        ${clubes
          .map((c) => {
            const on = state.stats.selecionados.includes(c.id);
            return `<button type="button" class="club-chip ${on ? "on" : ""}" data-clube="${c.id}">
              ${logo(c.logo)} ${c.clube}
            </button>`;
          })
          .join("")}
      </div>
    </div>
    <div class="filters-row">
      <div class="tabs subtabs" id="tabs-grupo">
        ${Object.entries(grupos)
          .map(
            ([k, lab]) =>
              `<button class="tab ${state.stats.grupo === k ? "active" : ""}" data-grupo="${k}" type="button">${lab}</button>`
          )
          .join("")}
      </div>
      <div class="modo-toggle">
        <button type="button" class="chip-btn ${state.stats.modo === "media" ? "on" : ""}" data-modo="media">Média / jogo</button>
        <button type="button" class="chip-btn ${state.stats.modo === "soma" ? "on" : ""}" data-modo="soma">Total</button>
      </div>
    </div>
    <section class="section">
      <h2 class="section-title">${grupos[state.stats.grupo] || "Grupo"}</h2>
      ${corpo}
    </section>
  `;
}

function bindArtilharia() {
  $("#art-pos")?.addEventListener("change", (ev) => {
    state.art.posicao = ev.target.value;
    refreshArtilharia();
  });
  $("#art-clube")?.addEventListener("change", (ev) => {
    state.art.clube_id = ev.target.value;
    refreshArtilharia();
  });
  $("#art-nac")?.addEventListener("change", (ev) => {
    state.art.nacionalidade = ev.target.value;
    refreshArtilharia();
  });
  $("#tbl-art")?.querySelectorAll("th.sortable").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (state.art.sort === key) state.art.ordem = state.art.ordem === "desc" ? "asc" : "desc";
      else {
        state.art.sort = key;
        state.art.ordem = "desc";
      }
      refreshArtilharia();
    });
  });
}

function refreshArtilharia() {
  const box = $("#art-box");
  if (!box || !state.dados) return;
  box.innerHTML = tabelaArtilharia(state.dados.artilharia, state.dados.artilharia_filtros);
  bindArtilharia();
}

function bindStatsPanel() {
  document.querySelectorAll("[data-clube]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = Number(btn.dataset.clube);
      const i = state.stats.selecionados.indexOf(id);
      if (i >= 0) state.stats.selecionados.splice(i, 1);
      else if (state.stats.selecionados.length < 5) state.stats.selecionados.push(id);
      await loadStatsLiga(1);
      paintStats();
    });
  });
  $("#tabs-grupo")?.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-grupo]");
    if (!btn) return;
    state.stats.grupo = btn.dataset.grupo;
    await loadStatsLiga(1);
    paintStats();
  });
  document.querySelectorAll("[data-modo]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.stats.modo = btn.dataset.modo;
      paintStats();
    });
  });
  document.querySelectorAll(".pager-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const p = Number(btn.dataset.page);
      if (p >= 1) {
        await loadStatsLiga(p);
        paintStats();
      }
    });
  });
  document.querySelectorAll("#painel-stats th.sortable").forEach((th) => {
    th.addEventListener("click", async () => {
      const key = th.dataset.sort;
      if (state.stats.sort === key) state.stats.ordem = state.stats.ordem === "desc" ? "asc" : "desc";
      else {
        state.stats.sort = key;
        state.stats.ordem = "desc";
      }
      await loadStatsLiga(state.stats.data?.page || 1);
      paintStats();
    });
  });
}

function paintStats() {
  const painel = $("#painel-stats");
  if (!painel) return;
  painel.innerHTML = renderStatsPanel();
  bindStatsPanel();
}

function render(dados) {
  state.dados = dados;
  state.rodadaIdx = indexRodadaInicial(dados.rodadas || [], dados.rodada_destaque);
  const temps = dados.temporadas || [];
  $("#conteudo").innerHTML = `
    <div class="league-hero">
      <div class="league-hero-main">
        ${logo(dados.logo, 48)}
        <div>
          <div class="eyebrow">${dados.pais || "Campeonato"}</div>
          <h1 class="page-title">${dados.nome || "Liga"}</h1>
        </div>
      </div>
      <label class="season-select">
        Temporada
        <select id="temporada">
          ${temps.map((t) => `<option value="${t}" ${t === dados.temporada ? "selected" : ""}>${t}</option>`).join("")}
        </select>
      </label>
    </div>

    <div class="tabs" id="tabs">
      <button class="tab ${state.aba === "classificacao" ? "active" : ""}" data-tab="classificacao" type="button">Classificação</button>
      <button class="tab ${state.aba === "rodadas" ? "active" : ""}" data-tab="rodadas" type="button">Rodadas</button>
      <button class="tab ${state.aba === "artilharia" ? "active" : ""}" data-tab="artilharia" type="button">Artilharia</button>
      <button class="tab ${state.aba === "estatisticas" ? "active" : ""}" data-tab="estatisticas" type="button">Estatísticas</button>
    </div>

    <section class="section ${state.aba === "classificacao" ? "" : "hidden"}" data-sec="classificacao">
      <div id="classif-box">${tabelaClassificacao(dados.classificacao)}</div>
    </section>

    <section class="section ${state.aba === "rodadas" ? "" : "hidden"}" data-sec="rodadas">
      <div id="rodadas-box">${rodadasNavHtml(dados.rodadas || [], state.rodadaIdx)}</div>
    </section>

    <section class="section ${state.aba === "artilharia" ? "" : "hidden"}" data-sec="artilharia">
      <div class="page-heading page-heading-center">
        <h2 class="page-title" style="font-size:clamp(1.6rem,3vw,2rem)">Artilharia</h2>
      </div>
      <div id="art-box">${tabelaArtilharia(dados.artilharia, dados.artilharia_filtros)}</div>
    </section>

    <section class="section ${state.aba === "estatisticas" ? "" : "hidden"}" data-sec="estatisticas">
      <div id="painel-stats"><div class="loading">Carregando estatísticas…</div></div>
    </section>
  `;

  document.title = dados.nome || "Liga";
  bindArtilharia();
  function bindClassif() {
    $("#tbl-classif")?.querySelectorAll("th.sortable").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.dataset.csort;
        if (classifSort.key === key) classifSort.ordem = classifSort.ordem === "desc" ? "asc" : "desc";
        else {
          classifSort.key = key;
          classifSort.ordem = "desc";
        }
        $("#classif-box").innerHTML = tabelaClassificacao(state.dados.classificacao);
        bindClassif();
      });
    });
  }
  bindClassif();
  bindRodadasNav(dados.rodadas || []);

  const secs = [...document.querySelectorAll("[data-sec]")];
  async function showTab(name) {
    state.aba = name;
    const url = new URL(location.href);
    url.searchParams.set("aba", name);
    history.replaceState(null, "", url);
    secs.forEach((s) => s.classList.toggle("hidden", s.dataset.sec !== name));
    document.querySelectorAll("#tabs .tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    if (name === "estatisticas") {
      await loadStatsLiga(1);
      paintStats();
    }
  }
  $("#tabs").addEventListener("click", (ev) => {
    const btn = ev.target.closest(".tab");
    if (btn) showTab(btn.dataset.tab);
  });
  $("#temporada").addEventListener("change", (ev) => carregar(ev.target.value));

  if (state.aba === "estatisticas") {
    loadStatsLiga(1).then(paintStats).catch((e) => {
      $("#painel-stats").innerHTML = `<div class="error">${e.message}</div>`;
    });
  }
}

async function carregar(temporada = null) {
  const id = ligaId();
  if (!id) {
    $("#conteudo").innerHTML = `<div class="error">Liga inválida.</div>`;
    return;
  }
  $("#conteudo").innerHTML = `<div class="loading">Carregando liga…</div>`;
  const qs = temporada ? `?temporada=${temporada}` : "";
  const res = await fetch(`/api/liga/${id}${qs}`);
  if (!res.ok) {
    $("#conteudo").innerHTML = `<div class="error">Liga não encontrada.</div>`;
    return;
  }
  state.stats.selecionados = [];
  render(await res.json());
}

carregar();
