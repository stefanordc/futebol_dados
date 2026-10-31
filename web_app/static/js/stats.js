import { minutosChartsHtml } from "./minutos-charts.js";
import { pctBarsHtml } from "./pct-bars.js";

const $ = (sel, el = document) => el.querySelector(sel);

function n(v, dig = 1) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("pt-BR", {
    minimumFractionDigits: dig,
    maximumFractionDigits: dig,
  });
}

/** Gols (e contagens inteiras) nunca com casa decimal no Total. */
const INT_TOTAL = new Set([
  "gols",
  "assistencias",
  "chutes_total",
  "chutes",
  "certas",
  "desarmes",
  "passes_certos",
  "jogos",
  "v",
  "e",
  "d",
  "amarelos",
  "vermelhos",
  "faltas",
]);

function isGolsKey(chave) {
  const k = String(chave || "").toLowerCase();
  return k === "gols" || k.startsWith("gols_") || k.endsWith("_gols");
}

function digValor(chave, v, { media = false } = {}) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  if (isGolsKey(chave) && !media) return n(Math.round(Number(v)), 0);
  if (chave === "rating" || String(chave).includes("posse") || String(chave).startsWith("pct_")) {
    return n(v, 2);
  }
  if (media) return n(v, 2);
  if (INT_TOTAL.has(chave) || Math.abs(Number(v) - Math.round(Number(v))) < 1e-9) {
    return n(Math.round(Number(v)), 0);
  }
  return n(v, 2);
}

function img(src, cls = "mini-av") {
  if (!src) return "";
  return `<img src="${src}" class="${cls}" alt="" loading="lazy" decoding="async" onerror="this.style.opacity=.25" />`;
}

function cellEntity(foto, nome, href = null) {
  const label = nome || "—";
  const text = href ? `<a class="entity-link" href="${href}">${label}</a>` : `<span>${label}</span>`;
  return `<td><div class="cell-inner">${img(foto)}${text}</div></td>`;
}

function thSort(key, label, cur, ordem) {
  const mark = cur === key ? (ordem === "desc" ? " ↓" : " ↑") : "";
  return `<th class="sortable" data-sort="${key}">${label}${mark}</th>`;
}

let state = {
  paises: [],
  ligas: [],
  clubes: [],
  pais: "",
  campeonatoId: null,
  temporada: null,
  temporadas: [],
  grupos: {},
  aba: "coletivas",
  subGrupo: "apostas",
  modo: "soma",
  page: 1,
  ordenar: null,
  ordem: "desc",
  coletivas: null,
  metricaIndiv: "gols",
  filtroPos: "",
  filtroClube: "", // toolbar: clube comum ("" = todos)
  filtroNac: "",
  sortIndiv: "valor",
  ordemIndiv: "desc",
  sortTec: "pts",
  ordemTec: "desc",
  sortArb: "jogos",
  ordemArb: "desc",
  metaReady: false,
  mapaClubeId: null,
  mapaJogadorId: null,
  finData: null,
  finFiltro: "todos", // todos | gol | certa | errada
  mando: "todos", // todos | casa | fora — toolbar comum
};

function modoToggleHtml() {
  return `
    <div class="modo-toggle">
      <button type="button" class="chip-btn ${state.modo === "media" ? "on" : ""}" data-modo="media">Média / jogo</button>
      <button type="button" class="chip-btn ${state.modo === "soma" ? "on" : ""}" data-modo="soma">Total</button>
    </div>`;
}

function bindModo(root, reload) {
  root.querySelectorAll("[data-modo]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.modo = btn.dataset.modo;
      reload();
    });
  });
}

function filtrarMapa(mapa) {
  const f = state.finFiltro || "todos";
  if (f === "todos") return mapa || [];
  const classe = f === "errada" ? "outra" : f;
  return (mapa || []).filter((s) => s.classe === classe);
}

function shotMapHtml(mapa, titulo) {
  const filtrado = filtrarMapa(mapa);
  const dots = filtrado
    .map((s) => {
      const cls = s.classe === "gol" ? "gol" : s.classe === "certa" ? "certa" : "outra";
      return `<span class="shot-dot stats-shot ${cls}" style="left:${s.left}%;top:${s.top}%" title="${s.jogador || ""} · ${s.tipo_evento || ""} · ${s.distancia_m ?? "—"}m"></span>`;
    })
    .join("");
  const chip = (key, label) =>
    `<button type="button" class="chip-btn ${state.finFiltro === key ? "on" : ""}" data-fin="${key}">${label}</button>`;
  return `
    <div class="fin-map-card">
      <div class="fin-map-head">
        <strong>${titulo || "Mapa de finalizações"}</strong>
        <div class="fin-legend">
          <span><i class="lg gol"></i> Gol</span>
          <span><i class="lg certa"></i> Certa</span>
          <span><i class="lg outra"></i> Errada</span>
        </div>
      </div>
      <div class="fin-filtros modo-toggle">
        ${chip("todos", "Todas")}
        ${chip("gol", "Gols")}
        ${chip("certa", "Certas")}
        ${chip("errada", "Erradas")}
      </div>
      <div class="pitch-wrap stats-pitch">
        <div class="pitch-lines">
          <div class="halfway"></div>
          <div class="circle"></div>
          <div class="box top"></div>
          <div class="box bottom"></div>
        </div>
        ${dots || `<div class="empty" style="position:absolute;inset:0;display:grid;place-items:center">Sem finalizações</div>`}
      </div>
      <div class="fin-map-note">Ataque em direção ao topo · ${filtrado.length} finalização${filtrado.length === 1 ? "" : "ões"}</div>
    </div>`;
}

function bindFinFiltro(painel, getMapa, getTitulo) {
  painel.querySelectorAll("[data-fin]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const next = btn.dataset.fin;
      if (!next || next === state.finFiltro) return;
      state.finFiltro = next;
      const card = painel.querySelector(".fin-map-card");
      if (!card) return;
      const tmp = document.createElement("div");
      tmp.innerHTML = shotMapHtml(getMapa(), getTitulo());
      card.replaceWith(tmp.firstElementChild);
      bindFinFiltro(painel, getMapa, getTitulo);
    });
  });
}

function scopeParams(extra = {}) {
  const qs = new URLSearchParams(extra);
  if (state.pais) qs.set("pais", state.pais);
  if (state.campeonatoId) qs.set("campeonato_id", String(state.campeonatoId));
  if (state.temporada) qs.set("temporada", state.temporada);
  if (state.filtroClube) qs.set("clube_id", String(state.filtroClube));
  if (state.mando && state.mando !== "todos") qs.set("mando", state.mando);
  // mantém "/" da temporada (ex.: 2026/2027) legível para o FastAPI
  return qs.toString().replace(/%2F/gi, "/");
}

function clubesOrdenados() {
  return [...(state.clubes || [])].sort((a, b) =>
    (a.clube || "").localeCompare(b.clube || "", "pt", { sensitivity: "base" })
  );
}

async function loadMeta() {
  const res = await fetch(`/api/stats/meta?${scopeParams()}`);
  const data = await res.json();
  state.paises = data.paises || [];
  state.ligas = data.ligas || [];
  state.clubes = data.clubes || [];
  state.temporadas = data.temporadas || [];
  state.temporada = data.temporada;
  state.grupos = data.grupos || {};
  state.campeonatoId = data.campeonato_id ?? null;
  if (!state.subGrupo || !state.grupos[state.subGrupo]) {
    state.subGrupo = Object.keys(state.grupos)[0] || "apostas";
  }
  // se o clube filtrado saiu do escopo, volta para todos
  if (state.filtroClube && !state.clubes.some((c) => String(c.id) === String(state.filtroClube))) {
    state.filtroClube = "";
  }
  state.metaReady = true;
}

async function loadColetivas() {
  const extra = {
    grupo: state.subGrupo,
    page: String(state.page),
    page_size: "20",
    ordem: state.ordem,
  };
  if (state.ordenar) extra.ordenar = state.ordenar;
  if (state.filtroClube) extra.clube_id = String(state.filtroClube);
  // finalizações: mapa usa o mesmo filtro de clube da toolbar
  if (state.subGrupo === "finalizacoes" && state.filtroClube) {
    state.mapaClubeId = Number(state.filtroClube);
  }
  const res = await fetch(`/api/stats/coletivas?${scopeParams(extra)}`);
  if (!res.ok) throw new Error("Falha ao carregar coletivas");
  state.coletivas = await res.json();
  if (state.coletivas.temporada) state.temporada = state.coletivas.temporada;
  if (state.coletivas.temporadas?.length) state.temporadas = state.coletivas.temporadas;
  if (state.subGrupo === "finalizacoes" && state.coletivas.mapa_clube_id && !state.filtroClube) {
    state.mapaClubeId = state.coletivas.mapa_clube_id;
  }
}

async function loadLista(tipo, extra = {}) {
  const res = await fetch(`/api/stats/${tipo}?${scopeParams(extra)}`);
  if (!res.ok) throw new Error(`Falha ao carregar ${tipo}`);
  return res.json();
}

function tabelaColetivas(data, modo = "soma") {
  if (!data?.metricas?.length && data?.grupo !== "minutos") {
    return `<div class="empty">Sem dados coletivos.</div>`;
  }
  const mets = data.metricas || [];
  const media = modo === "media";
  const showCamp = !state.campeonatoId;

  return `
    <div class="table-wrap">
      <table class="data-table" id="tbl-col">
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
              const rowCls =
                data.grupo === "minutos" && r.clube_id === state.mapaClubeId ? "fin-row row-on" : data.grupo === "minutos" ? "fin-row" : "";
              return `<tr class="${rowCls}" data-clube="${r.clube_id || ""}">
              <td>${rank}</td>
              ${cellEntity(r.logo, r.clube, r.clube_id ? `/clube/${r.clube_id}` : null)}
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
                  const suf = String(m.chave).startsWith("pct_") && val != null ? "%" : "";
                  return `<td>${digValor(m.chave, val, { media })}${suf}</td>`;
                })
                .join("")}
            </tr>`;
            })
            .join("")}
        </tbody>
      </table>
    </div>`;
}

function mandoToggleHtml() {
  const chip = (k, lab) =>
    `<button type="button" class="chip-btn ${state.mando === k ? "on" : ""}" data-mando="${k}">${lab}</button>`;
  return `<div class="modo-toggle mando-toggle">${chip("todos", "Todos")}${chip("casa", "Casa")}${chip("fora", "Fora")}</div>`;
}

function paginacao(data) {
  if (!data || data.pages <= 1) return "";
  return `
    <div class="pager">
      <button type="button" class="pager-btn" data-page="${data.page - 1}" ${data.page <= 1 ? "disabled" : ""}>←</button>
      <span>${data.page}/${data.pages} · ${data.total}</span>
      <button type="button" class="pager-btn" data-page="${data.page + 1}" ${data.page >= data.pages ? "disabled" : ""}>→</button>
    </div>`;
}

function shell() {
  return `
    <div class="page-heading hero-heading page-heading-center">
      <h1 class="page-title">Estatísticas</h1>
    </div>
    <div class="stats-toolbar">
      <label>País
        <select id="sel-pais">
          <option value="">Todos</option>
          ${state.paises.map((p) => `<option value="${p}" ${p === state.pais ? "selected" : ""}>${p}</option>`).join("")}
        </select>
      </label>
      <label>Campeonato
        <select id="sel-liga">
          <option value="">Todos</option>
          ${state.ligas
            .map((l) => `<option value="${l.id}" ${l.id === state.campeonatoId ? "selected" : ""}>${l.nome}</option>`)
            .join("")}
        </select>
      </label>
      <label>Clube
        <select id="sel-clube">
          <option value="">Todos os clubes</option>
          ${clubesOrdenados()
            .map((c) => `<option value="${c.id}" ${String(state.filtroClube) === String(c.id) ? "selected" : ""}>${c.clube}</option>`)
            .join("")}
        </select>
      </label>
      <label>Mando
        <select id="sel-mando">
          <option value="todos" ${state.mando === "todos" ? "selected" : ""}>Todos</option>
          <option value="casa" ${state.mando === "casa" ? "selected" : ""}>Casa</option>
          <option value="fora" ${state.mando === "fora" ? "selected" : ""}>Fora</option>
        </select>
      </label>
      <label>Temporada
        <select id="sel-temp">
          ${state.temporadas.map((t) => `<option value="${t}" ${t === state.temporada ? "selected" : ""}>${t}</option>`).join("")}
        </select>
      </label>
      ${
        state.campeonatoId
          ? `<a class="camp-open" href="/liga/${state.campeonatoId}?aba=estatisticas">No campeonato →</a>`
          : ""
      }
    </div>
    <div class="tabs" id="tabs-main">
      <button class="tab ${state.aba === "coletivas" ? "active" : ""}" data-tab="coletivas" type="button">Coletivas</button>
      <button class="tab ${state.aba === "individuais" ? "active" : ""}" data-tab="individuais" type="button">Individuais</button>
      <button class="tab ${state.aba === "tecnicos" ? "active" : ""}" data-tab="tecnicos" type="button">Técnicos</button>
      <button class="tab ${state.aba === "arbitros" ? "active" : ""}" data-tab="arbitros" type="button">Árbitros</button>
    </div>
    <div id="painel"></div>
  `;
}

function bindSort(root, getKey, setKey, getOrd, setOrd, reload) {
  root.querySelectorAll("th.sortable").forEach((th) => {
    th.addEventListener("click", async () => {
      const key = th.dataset.sort;
      if (getKey() === key) setOrd(getOrd() === "desc" ? "asc" : "desc");
      else {
        setKey(key);
        setOrd("desc");
      }
      await reload();
    });
  });
}

function tabelaFinalizacoesClubes(data) {
  const th = (key, label) => thSort(key, label, data.ordenar, data.ordem);
  const media = state.modo === "media";
  const showCamp = !state.campeonatoId;
  const val = (r, k) => (media ? r[`${k}_media`] : r[k]);
  return `
    <div class="table-wrap">
      <table class="data-table" id="tbl-fin-clube">
        <thead>
          <tr>
            <th>#</th>
            ${th("clube", "Clube")}
            ${showCamp ? `<th>Campeonato</th>` : ""}
            ${th("jogos", "J")}
            ${th("chutes", media ? "Chutes/J" : "Chutes")}
            ${th("certas", media ? "Certas/J" : "Certas")}
            ${th("gols", media ? "Gols/J" : "Gols")}
            ${th("dist_chute", "Dist. chute (m)")}
            ${th("dist_certa", "Dist. certa (m)")}
            ${th("dist_gol", "Dist. gol (m)")}
          </tr>
        </thead>
        <tbody>
          ${(data.linhas || [])
            .map((r, i) => {
              const rank = (data.page - 1) * data.page_size + i + 1;
              const on = r.clube_id === state.mapaClubeId ? "row-on" : "";
              return `<tr class="fin-row ${on}" data-clube="${r.clube_id}">
              <td>${rank}</td>
              ${cellEntity(r.logo, r.clube, `/clube/${r.clube_id}`)}
              ${showCamp ? `<td>${r.campeonato || "—"}</td>` : ""}
              <td>${r.jogos}</td>
              <td>${n(val(r, "chutes"), media ? 2 : 0)}</td>
              <td>${n(val(r, "certas"), media ? 2 : 0)}</td>
              <td><strong>${n(val(r, "gols"), media ? 2 : 0)}</strong></td>
              <td>${n(r.dist_chute, 1)}</td>
              <td>${n(r.dist_certa, 1)}</td>
              <td>${n(r.dist_gol, 1)}</td>
            </tr>`;
            })
            .join("")}
        </tbody>
      </table>
    </div>`;
}

async function renderColetivas() {
  const painel = $("#painel");
  painel.innerHTML = `<div class="loading">Carregando…</div>`;
  try {
    await loadColetivas();
  } catch (e) {
    painel.innerHTML = `<div class="error">${e.message}</div>`;
    return;
  }
  const grupos = state.grupos || {};
  const isFin = state.subGrupo === "finalizacoes";
  const isMin = state.subGrupo === "minutos";
  const isApostas = state.subGrupo === "apostas";
  const clubeMapa = (state.coletivas.linhas || []).find((r) => r.clube_id === state.mapaClubeId);
  const clubeNome =
    (state.filtroClube && state.clubes.find((c) => String(c.id) === String(state.filtroClube))?.clube) ||
    null;

  let corpo = `${tabelaColetivas(state.coletivas, state.modo)}${paginacao(state.coletivas)}`;
  if (isApostas) {
    const ap = state.coletivas.apostas || {};
    const jogos = ap.jogos || 0;
    corpo = `
      ${pctBarsHtml(ap.barras, {
        title: "Mercados",
        meta: `${jogos} jogo${jogos === 1 ? "" : "s"} no escopo`,
      })}
      <section class="section placares-freq">
        <h2 class="section-title">Placares mais frequentes</h2>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>#</th><th>Placar</th><th>Jogos</th><th>%</th></tr></thead>
            <tbody>
              ${(ap.placares || [])
                .map(
                  (p, i) => `<tr>
                <td>${i + 1}</td>
                <td>${p.placar}</td>
                <td>${p.jogos}</td>
                <td>${n(p.pct, 1)}%</td>
              </tr>`
                )
                .join("") || `<tr><td colspan="4">Sem placares.</td></tr>`}
            </tbody>
          </table>
        </div>
      </section>`;
  } else if (isFin) {
    corpo = `<div class="fin-layout">
      <div>
        ${tabelaFinalizacoesClubes(state.coletivas)}
        ${paginacao(state.coletivas)}
        <p class="fin-hint">${state.filtroClube ? "Mapa do clube filtrado." : "Clique em um clube para ver o mapa de finalizações."}</p>
      </div>
      ${shotMapHtml(state.coletivas.mapa, clubeMapa ? clubeMapa.clube : clubeNome || "Mapa")}
    </div>`;
  } else if (isMin) {
    const titulo = clubeNome || "Todos os clubes";
    corpo = `<div class="minutos-only">${minutosChartsHtml(state.coletivas.minutos, titulo)}</div>`;
  }

  painel.innerHTML = `
    <div class="filters-row between">
      <div class="tabs subtabs" id="tabs-grupo">
        ${Object.entries(grupos)
          .map(([k, lab]) => `<button class="tab ${state.subGrupo === k ? "active" : ""}" data-grupo="${k}" type="button">${lab}</button>`)
          .join("")}
      </div>
      <div class="filters-right">
        ${isMin || isApostas ? "" : modoToggleHtml()}
      </div>
    </div>
    ${
      isApostas
        ? corpo
        : `<section class="section">
      <h2 class="section-title">${grupos[state.subGrupo] || ""}</h2>
      ${corpo}
    </section>`
    }
  `;
  $("#tabs-grupo")?.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-grupo]");
    if (!btn) return;
    state.subGrupo = btn.dataset.grupo;
    state.page = 1;
    state.ordenar = null;
    state.ordem = "desc";
    if (!state.filtroClube) state.mapaClubeId = null;
    await renderColetivas();
  });
  bindModo(painel, renderColetivas);
  if (isMin || isApostas) {
    /* sem sort de tabela */
  } else if (isFin) {
    bindFinFiltro(
      painel,
      () => state.coletivas?.mapa,
      () => {
        const c = (state.coletivas?.linhas || []).find((r) => r.clube_id === state.mapaClubeId);
        return c ? c.clube : clubeNome || "Mapa";
      }
    );
  }
  painel.querySelectorAll(".pager-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const p = Number(btn.dataset.page);
      if (p >= 1) {
        state.page = p;
        await renderColetivas();
      }
    });
  });
  painel.querySelectorAll(".fin-row").forEach((row) => {
    row.addEventListener("click", async (ev) => {
      if (ev.target.closest("a")) return;
      if (state.filtroClube) return;
      state.mapaClubeId = Number(row.dataset.clube);
      await renderColetivas();
    });
  });
  if (!isMin && !isApostas) {
    bindSort(
      painel,
      () => state.ordenar,
      (v) => (state.ordenar = v),
      () => state.ordem,
      (v) => (state.ordem = v),
      renderColetivas
    );
  }
}

async function renderIndividuais() {
  const painel = $("#painel");
  painel.innerHTML = `<div class="loading">Carregando…</div>`;
  const metrica = state.metricaIndiv || "gols";
  const isFin = metrica === "finalizacoes";

  if (isFin) {
    const extra = {
      escopo: "jogador",
      limite: "50",
      ordenar: state.sortIndiv === "valor" ? "gols" : state.sortIndiv,
      ordem: state.ordemIndiv,
    };
    if (state.filtroClube) extra.clube_id = state.filtroClube;
    if (state.mapaJogadorId) extra.jogador_id = String(state.mapaJogadorId);
    const data = await loadLista("finalizacoes", extra);
    state.finData = data;
    if (data.mapa_jogador_id) state.mapaJogadorId = data.mapa_jogador_id;
    const th = (key, label) => thSort(key, label, data.ordenar, data.ordem);
    const media = state.modo === "media";
    const val = (r, k) => (media ? r[`${k}_media`] : r[k]);
    const jogMapa = (data.linhas || []).find((r) => r.jogador_id === state.mapaJogadorId);

    painel.innerHTML = `
      <div class="filters-row between">
        <div class="tabs subtabs" id="tabs-metrica">
          ${indivMetricTabs(metrica)}
        </div>
        ${modoToggleHtml()}
      </div>
      <section class="section">
        <h2 class="section-title">Individuais — Finalizações</h2>
        <div class="fin-layout">
          <div>
            <div class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>#</th>${th("nome", "Jogador")}${th("clube", "Clube")}${th("jogos", "J")}
                    ${th("chutes", media ? "Chutes/J" : "Chutes")}
                    ${th("certas", media ? "Certas/J" : "Certas")}
                    ${th("gols", media ? "Gols/J" : "Gols")}
                    ${th("dist_chute", "Dist. chute")}
                    ${th("dist_certa", "Dist. certa")}
                    ${th("dist_gol", "Dist. gol")}
                  </tr>
                </thead>
                <tbody>
                  ${(data.linhas || [])
                    .map(
                      (r) => `<tr class="fin-row ${r.jogador_id === state.mapaJogadorId ? "row-on" : ""}" data-jogador="${r.jogador_id}">
                    <td>${r.posicao_rank}</td>
                    ${cellEntity(r.foto, r.nome, r.jogador_id ? `/jogador/${r.jogador_id}` : null)}
                    ${cellEntity(r.clube_logo, r.clube, r.clube_id ? `/clube/${r.clube_id}` : null)}
                    <td>${r.jogos}</td>
                    <td>${n(val(r, "chutes"), media ? 2 : 0)}</td>
                    <td>${n(val(r, "certas"), media ? 2 : 0)}</td>
                    <td><strong>${n(val(r, "gols"), media ? 2 : 0)}</strong></td>
                    <td>${n(r.dist_chute, 1)}</td>
                    <td>${n(r.dist_certa, 1)}</td>
                    <td>${n(r.dist_gol, 1)}</td>
                  </tr>`
                    )
                    .join("") || `<tr><td colspan="10">Sem dados.</td></tr>`}
                </tbody>
              </table>
            </div>
            <p class="fin-hint">Clique em um jogador para ver o mapa.</p>
          </div>
          ${shotMapHtml(data.mapa, jogMapa ? jogMapa.nome : "Mapa")}
        </div>
      </section>`;

    $("#tabs-metrica").addEventListener("click", async (ev) => {
      const btn = ev.target.closest("[data-m]");
      if (!btn) return;
      state.metricaIndiv = btn.dataset.m;
      state.sortIndiv = "valor";
      state.ordemIndiv = "desc";
      state.mapaJogadorId = null;
      await renderIndividuais();
    });
    bindModo(painel, renderIndividuais);
    bindFinFiltro(
      painel,
      () => state.finData?.mapa,
      () => {
        const j = (state.finData?.linhas || []).find((r) => r.jogador_id === state.mapaJogadorId);
        return j ? j.nome : "Mapa";
      }
    );
    painel.querySelectorAll(".fin-row").forEach((row) => {
      row.addEventListener("click", async () => {
        state.mapaJogadorId = Number(row.dataset.jogador);
        await renderIndividuais();
      });
    });
    bindSort(
      painel,
      () => state.sortIndiv,
      (v) => (state.sortIndiv = v),
      () => state.ordemIndiv,
      (v) => (state.ordemIndiv = v),
      renderIndividuais
    );
    return;
  }

  const data = await loadLista("individuais", {
    metrica,
    limite: "50",
    ordenar: state.sortIndiv,
    ordem: state.ordemIndiv,
    ...(state.filtroPos ? { posicao: state.filtroPos } : {}),
    ...(state.filtroClube ? { clube_id: state.filtroClube } : {}),
    ...(state.filtroNac ? { nacionalidade: state.filtroNac } : {}),
  });
  const f = data.filtros || {};
  const th = (key, label) => thSort(key, label, state.sortIndiv, state.ordemIndiv);
  const showCamp = !state.campeonatoId;
  const media = state.modo === "media";

  painel.innerHTML = `
    <div class="filters-row between">
      <div class="tabs subtabs" id="tabs-metrica">${indivMetricTabs(metrica, f.metricas)}</div>
      ${modoToggleHtml()}
    </div>
    <div class="filters-row">
      <label>Posição
        <select id="ind-pos"><option value="">Todas</option>${(f.posicoes || []).map((p) => `<option value="${p}" ${state.filtroPos === p ? "selected" : ""}>${p}</option>`).join("")}</select>
      </label>
      <label>Nacionalidade
        <select id="ind-nac"><option value="">Todas</option>${(f.nacionalidades || []).map((p) => `<option value="${p}" ${state.filtroNac === p ? "selected" : ""}>${p}</option>`).join("")}</select>
      </label>
    </div>
    <section class="section">
      <h2 class="section-title">Individuais — ${(f.metricas || {})[metrica] || metrica}</h2>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>#</th>
              ${th("nome", "Jogador")}
              ${th("clube", "Clube")}
              ${showCamp ? th("campeonato", "Campeonato") : ""}
              ${th("posicao", "Posição")}
              ${th("nacionalidade", "Nacionalidade")}
              ${th("valor", media ? "Média/J" : "Total")}
              ${th("jogos", "Jogos")}
              ${th("rating_medio", "Nota")}
            </tr>
          </thead>
          <tbody>
            ${(data.itens || [])
              .map((r) => {
                const shown =
                  metrica === "rating"
                    ? r.valor_media ?? r.valor
                    : media
                      ? r.valor_media
                      : r.valor_soma ?? r.valor;
                return `<tr>
              <td>${r.posicao_rank}</td>
              ${cellEntity(r.foto, r.nome, r.jogador_id || r.id ? `/jogador/${r.jogador_id || r.id}` : null)}
              ${cellEntity(r.clube_logo, r.clube, r.clube_id ? `/clube/${r.clube_id}` : null)}
              ${showCamp ? `<td>${r.campeonato || "—"}</td>` : ""}
              <td>${r.posicao || "—"}</td>
              <td>${r.nacionalidade || "—"}</td>
              <td><strong>${digValor(metrica, shown, { media: metrica === "rating" || media })}</strong></td>
              <td>${r.jogos}</td>
              <td>${n(r.rating_medio, 2)}</td>
            </tr>`;
              })
              .join("") || `<tr><td colspan="9">Sem dados.</td></tr>`}
          </tbody>
        </table>
      </div>
    </section>`;

  $("#tabs-metrica").addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-m]");
    if (!btn) return;
    state.metricaIndiv = btn.dataset.m;
    state.sortIndiv = "valor";
    state.ordemIndiv = "desc";
    await renderIndividuais();
  });
  $("#ind-pos").addEventListener("change", async (ev) => {
    state.filtroPos = ev.target.value;
    await renderIndividuais();
  });
  $("#ind-nac").addEventListener("change", async (ev) => {
    state.filtroNac = ev.target.value;
    await renderIndividuais();
  });
  bindModo(painel, renderIndividuais);
  bindSort(
    painel,
    () => state.sortIndiv,
    (v) => (state.sortIndiv = v),
    () => state.ordemIndiv,
    (v) => (state.ordemIndiv = v),
    renderIndividuais
  );
}

function indivMetricTabs(ativa, metricas) {
  const base = {
    gols: "Gols",
    assistencias: "Assistências",
    rating: "Nota",
    xg: "xG",
    xa: "xA",
    chutes_total: "Chutes",
    desarmes: "Desarmes",
    passes_certos: "Passes certos",
    ...(metricas || {}),
    finalizacoes: "Finalizações",
  };
  return Object.entries(base)
    .map(([k, lab]) => `<button class="tab ${ativa === k ? "active" : ""}" data-m="${k}" type="button">${lab}</button>`)
    .join("");
}

async function renderTecnicos() {
  const painel = $("#painel");
  painel.innerHTML = `<div class="loading">Carregando…</div>`;
  const data = await loadLista("tecnicos", { ordenar: state.sortTec, ordem: state.ordemTec });
  const th = (key, label) => thSort(key, label, state.sortTec, state.ordemTec);
  const media = state.modo === "media";
  const per = (v, j) => (j ? Number(v) / j : null);
  painel.innerHTML = `
    <div class="filters-row between">
      <div></div>
      ${modoToggleHtml()}
    </div>
    <section class="section">
      <h2 class="section-title">Técnicos</h2>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>#</th>${th("nome", "Técnico")}${th("clube", "Clube")}
              ${th("jogos", "J")}
              ${th("v", media ? "V/J" : "V")}<th>${media ? "E/J" : "E"}</th><th>${media ? "D/J" : "D"}</th>
              ${th("clean_sheets", media ? "CS/J" : "CS")}
              ${th("clean_goals", media ? "CG/J" : "CG")}
              ${th("pts", media ? "Pts/J" : "Pts")}
            </tr>
          </thead>
          <tbody>
            ${(data.itens || [])
              .map((r) => {
                const j = r.jogos || 1;
                return `<tr>
              <td>${r.posicao}</td>
              ${cellEntity(r.foto, r.nome, `/tecnico/${r.id}`)}
              <td>${r.clube || "—"}</td>
              <td>${r.jogos}</td>
              <td>${media ? n(per(r.v, j), 2) : r.v}</td>
              <td>${media ? n(per(r.e, j), 2) : r.e}</td>
              <td>${media ? n(per(r.d, j), 2) : r.d}</td>
              <td title="Clean sheets">${media ? n(r.clean_sheets_media, 2) : r.clean_sheets ?? 0}</td>
              <td title="Clean goals">${media ? n(r.clean_goals_media, 2) : r.clean_goals ?? 0}</td>
              <td><strong>${media ? n(r.pts_por_jogo, 2) : r.pts}</strong></td>
            </tr>`;
              })
              .join("") || `<tr><td colspan="10">Sem dados.</td></tr>`}
          </tbody>
        </table>
      </div>
    </section>`;
  bindModo(painel, renderTecnicos);
  bindSort(
    painel,
    () => state.sortTec,
    (v) => (state.sortTec = v),
    () => state.ordemTec,
    (v) => (state.ordemTec = v),
    renderTecnicos
  );
}

async function renderArbitros() {
  const painel = $("#painel");
  painel.innerHTML = `<div class="loading">Carregando…</div>`;
  const data = await loadLista("arbitros", { ordenar: state.sortArb, ordem: state.ordemArb });
  const th = (key, label) => thSort(key, label, state.sortArb, state.ordemArb);
  const media = state.modo === "media";
  painel.innerHTML = `
    <div class="filters-row between">
      <div></div>
      ${modoToggleHtml()}
    </div>
    <section class="section">
      <h2 class="section-title">Árbitros</h2>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>#</th>${th("nome", "Árbitro")}<th>País</th>
              ${th("jogos", "Jogos")}
              ${th("amarelos_por_jogo", media ? "Amarelos/J" : "Amarelos")}
              ${th("vermelhos_por_jogo", media ? "Vermelhos/J" : "Vermelhos")}
              ${th("faltas_por_jogo", media ? "Faltas/J" : "Faltas")}
            </tr>
          </thead>
          <tbody>
            ${(data.itens || [])
              .map(
                (r) => `<tr>
              <td>${r.posicao}</td>
              ${cellEntity(r.foto, r.nome, `/arbitro/${r.id}`)}
              <td>${r.pais || "—"}</td>
              <td>${r.jogos}</td>
              <td>${media ? n(r.amarelos_por_jogo, 2) : n(r.amarelos, 0)}</td>
              <td>${media ? n(r.vermelhos_por_jogo, 2) : n(r.vermelhos, 0)}</td>
              <td>${media ? n(r.faltas_por_jogo, 2) : n(r.faltas, 0)}</td>
            </tr>`
              )
              .join("") || `<tr><td colspan="7">Sem dados.</td></tr>`}
          </tbody>
        </table>
      </div>
    </section>`;
  bindModo(painel, renderArbitros);
  bindSort(
    painel,
    () => state.sortArb,
    (v) => (state.sortArb = v),
    () => state.ordemArb,
    (v) => (state.ordemArb = v),
    renderArbitros
  );
}

async function renderPainel() {
  if (state.aba === "coletivas") await renderColetivas();
  else if (state.aba === "individuais") await renderIndividuais();
  else if (state.aba === "tecnicos") await renderTecnicos();
  else if (state.aba === "arbitros") await renderArbitros();
}

function syncToolbarSelects() {
  const pais = $("#sel-pais");
  const liga = $("#sel-liga");
  const clube = $("#sel-clube");
  const mando = $("#sel-mando");
  const temp = $("#sel-temp");
  if (pais) {
    pais.innerHTML = `<option value="">Todos</option>${state.paises.map((p) => `<option value="${p}" ${p === state.pais ? "selected" : ""}>${p}</option>`).join("")}`;
  }
  if (liga) {
    liga.innerHTML = `<option value="">Todos</option>${state.ligas.map((l) => `<option value="${l.id}" ${l.id === state.campeonatoId ? "selected" : ""}>${l.nome}</option>`).join("")}`;
  }
  if (clube) {
    clube.innerHTML = `<option value="">Todos os clubes</option>${clubesOrdenados()
      .map((c) => `<option value="${c.id}" ${String(state.filtroClube) === String(c.id) ? "selected" : ""}>${c.clube}</option>`)
      .join("")}`;
  }
  if (mando) mando.value = state.mando || "todos";
  if (temp) {
    temp.innerHTML = state.temporadas.map((t) => `<option value="${t}" ${t === state.temporada ? "selected" : ""}>${t}</option>`).join("");
  }
}

async function refreshFilters() {
  await loadMeta();
  syncToolbarSelects();
  await renderPainel();
}

function bindShell() {
  $("#sel-pais").addEventListener("change", async (ev) => {
    state.pais = ev.target.value;
    state.campeonatoId = null;
    state.temporada = null;
    state.filtroClube = "";
    state.page = 1;
    await refreshFilters();
  });
  $("#sel-liga").addEventListener("change", async (ev) => {
    state.campeonatoId = ev.target.value ? Number(ev.target.value) : null;
    state.temporada = null;
    state.page = 1;
    state.filtroClube = "";
    await refreshFilters();
  });
  $("#sel-clube").addEventListener("change", async (ev) => {
    state.filtroClube = ev.target.value || "";
    state.mapaClubeId = state.filtroClube ? Number(state.filtroClube) : null;
    state.page = 1;
    // clube estreita campeonatos/temporadas compatíveis
    await refreshFilters();
  });
  $("#sel-mando").addEventListener("change", async (ev) => {
    state.mando = ev.target.value || "todos";
    state.page = 1;
    await renderPainel();
  });
  $("#sel-temp").addEventListener("change", async (ev) => {
    state.temporada = ev.target.value;
    state.filtroClube = "";
    state.page = 1;
    await refreshFilters();
  });
  $("#tabs-main").addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-tab]");
    if (!btn) return;
    state.aba = btn.dataset.tab;
    document.querySelectorAll("#tabs-main .tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === state.aba));
    await renderPainel();
  });
}

async function init() {
  try {
    $("#conteudo").innerHTML = `<div class="loading">Carregando…</div>`;
    await loadMeta();
    $("#conteudo").innerHTML = shell();
    bindShell();
    await renderPainel();
  } catch (e) {
    $("#conteudo").innerHTML = `<div class="error">${e.message}</div>`;
  }
}

init();
