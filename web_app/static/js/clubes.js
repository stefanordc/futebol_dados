import { setSiteFavicon } from "./favicon.js";

const $ = (sel, el = document) => el.querySelector(sel);

let state = {
  paises: [],
  ligas: [],
  clubes: [],
  pais: "",
  campeonatoId: null,
  temporada: null,
  temporadas: [],
};

function scopeQs() {
  const qs = new URLSearchParams();
  if (state.pais) qs.set("pais", state.pais);
  if (state.campeonatoId) qs.set("campeonato_id", String(state.campeonatoId));
  if (state.temporada) qs.set("temporada", state.temporada);
  return qs.toString().replace(/%2F/gi, "/");
}

async function loadMeta() {
  const res = await fetch(`/api/clubes/meta?${scopeQs()}`);
  if (!res.ok) throw new Error("Falha ao carregar filtros");
  const data = await res.json();
  state.paises = data.paises || [];
  state.ligas = data.ligas || [];
  state.temporadas = data.temporadas || [];
  state.temporada = data.temporada;
  state.campeonatoId = data.campeonato_id ?? null;
  state.clubes = data.clubes || [];
}

function clubCard(c) {
  const logo = c.logo
    ? `<img src="${c.logo}" alt="" class="club-tile-logo" loading="lazy" decoding="async" onerror="this.style.opacity=.2" />`
    : `<span class="club-tile-fallback">${(c.clube || "?").slice(0, 2).toUpperCase()}</span>`;
  return `<a class="club-tile" href="/clube/${c.id}" title="${c.clube || ""}">
    ${logo}
    <span class="club-tile-name">${c.clube || "—"}</span>
  </a>`;
}

function render() {
  const root = $("#conteudo");
  const clubes = [...(state.clubes || [])].sort((a, b) =>
    (a.clube || "").localeCompare(b.clube || "", "pt", { sensitivity: "base" })
  );
  root.innerHTML = `
    <div class="page-heading hero-heading page-heading-center">
      <h1 class="page-title">Clubes</h1>
    </div>
    <div class="stats-toolbar clubes-toolbar">
      <label>País
        <select id="sel-pais">
          <option value="">Todos</option>
          ${state.paises
            .map((p) => `<option value="${p}" ${p === state.pais ? "selected" : ""}>${p}</option>`)
            .join("")}
        </select>
      </label>
      <label>Campeonato
        <select id="sel-liga">
          <option value="">Todos</option>
          ${state.ligas
            .map(
              (l) =>
                `<option value="${l.id}" ${l.id === state.campeonatoId ? "selected" : ""}>${l.nome}</option>`
            )
            .join("")}
        </select>
      </label>
      ${
        state.temporadas.length
          ? `<label>Temporada
        <select id="sel-temp">
          ${state.temporadas
            .map((t) => `<option value="${t}" ${t === state.temporada ? "selected" : ""}>${t}</option>`)
            .join("")}
        </select>
      </label>`
          : ""
      }
    </div>
    <p class="muted clubes-count">${clubes.length} clube${clubes.length === 1 ? "" : "s"}</p>
    <div class="club-grid">
      ${clubes.map(clubCard).join("") || `<div class="empty">Nenhum clube neste filtro.</div>`}
    </div>
  `;

  $("#sel-pais")?.addEventListener("change", async (ev) => {
    state.pais = ev.target.value;
    state.campeonatoId = null;
    state.temporada = null;
    await refresh();
  });
  $("#sel-liga")?.addEventListener("change", async (ev) => {
    state.campeonatoId = ev.target.value ? Number(ev.target.value) : null;
    state.temporada = null;
    await refresh();
  });
  $("#sel-temp")?.addEventListener("change", async (ev) => {
    state.temporada = ev.target.value;
    await refresh();
  });
}

async function refresh() {
  $("#conteudo").innerHTML = `<div class="loading">Carregando clubes…</div>`;
  await loadMeta();
  render();
}

async function init() {
  setSiteFavicon();
  try {
    await loadMeta();
    render();
  } catch (e) {
    $("#conteudo").innerHTML = `<div class="error">${e.message}</div>`;
  }
}

init();
