import { openEditModal, pencilBtn } from "./edit.js";
import { setFavicon, setSiteFavicon } from "./favicon.js";
import { initNav } from "./nav.js";

const $ = (sel, el = document) => el.querySelector(sel);

function n(v, dig = 1) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("pt-BR", {
    minimumFractionDigits: dig,
    maximumFractionDigits: dig,
  });
}

function img(src, cls = "mini-av") {
  if (!src) return "";
  return `<img src="${src}" class="${cls}" alt="" loading="lazy" onerror="this.style.opacity=.25" />`;
}

const parts = location.pathname.split("/").filter(Boolean);
const tipo = parts[0]; // jogador | tecnico | arbitro
const id = Number(parts[1]);
const params = new URLSearchParams(location.search);

let state = {
  data: null,
  temporada: params.get("temporada") || null,
  grupo: params.get("grupo") || "resumo",
  modo: params.get("modo") === "media" ? "media" : "soma",
};

const TIPO_API = { jogador: "jogador", tecnico: "tecnico", arbitro: "arbitro" };
const TIPO_EDIT = { jogador: "jogador", tecnico: "tecnico", arbitro: "arbitro" };

async function load() {
  const api = TIPO_API[tipo];
  if (!api) throw new Error("Tipo inválido");
  const q = new URLSearchParams();
  if (state.temporada) q.set("temporada", state.temporada);
  const res = await fetch(`/api/${api}/${id}?${q.toString().replace(/%2F/gi, "/")}`);
  if (!res.ok) throw new Error("Não encontrado");
  state.data = await res.json();
  state.temporada = state.data.temporada;
  const grupos = state.data.estatisticas?.grupos || {};
  if (!grupos[state.grupo]) {
    state.grupo = Object.keys(grupos)[0] || "resumo";
  }
}

function syncUrl() {
  const q = new URLSearchParams();
  if (state.temporada) q.set("temporada", state.temporada);
  if (tipo === "jogador") {
    if (state.grupo && state.grupo !== "resumo") q.set("grupo", state.grupo);
    if (state.modo === "media") q.set("modo", "media");
  }
  const qs = q.toString().replace(/%2F/gi, "/");
  history.replaceState(null, "", `/${tipo}/${id}${qs ? `?${qs}` : ""}`);
}

function bindEdit() {
  const e = state.data.entidade;
  document.querySelectorAll(".edit-pencil").forEach((btn) => {
    btn.addEventListener("click", () => {
      openEditModal({
        tipo: TIPO_EDIT[tipo],
        id: e.id,
        nome: e.nome,
        foto: e.foto,
        onSaved: async () => {
          await load();
          await render();
        },
      });
    });
  });
}

function tabelaJogador() {
  const linhas = state.data.linhas || [];
  return `
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr><th>Campeonato</th><th>Clube</th><th>J</th><th>Min</th><th>Gols</th><th>Ast</th><th>Nota</th></tr>
        </thead>
        <tbody>
          ${linhas
            .map(
              (r) => `<tr>
            <td><a class="camp-link" href="/liga/${r.campeonato_id}">${r.campeonato}</a></td>
            <td><a class="entity-link" href="/clube/${r.clube_id}">${r.clube}</a></td>
            <td>${r.jogos}</td><td>${r.minutos ?? "—"}</td>
            <td>${r.gols ?? 0}</td><td>${r.assistencias ?? 0}</td>
            <td>${n(r.rating, 2)}</td>
          </tr>`
            )
            .join("") || `<tr><td colspan="7">Sem dados.</td></tr>`}
        </tbody>
      </table>
    </div>`;
}

function digStat(chave, v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const k = String(chave || "");
  if (k === "gols" || k === "gols_marcados" || k === "gols_sofridos" || k === "gols_contra") {
    return n(Math.round(Number(v)), 0);
  }
  if (
    chave === "rating" ||
    chave === "precisao_chutes" ||
    chave === "xg" ||
    chave === "xa" ||
    chave === "xgot" ||
    chave === "xg_xa" ||
    chave === "xg_sem_penalti" ||
    chave === "xgot_sofrido" ||
    chave === "gols_evitados"
  ) {
    return n(v, 2);
  }
  return Number.isInteger(Number(v)) || Math.abs(Number(v) - Math.round(Number(v))) < 1e-9
    ? n(Math.round(Number(v)), 0)
    : n(v, 2);
}

function statsJogador() {
  const est = state.data.estatisticas || {};
  const grupos = est.grupos || {};
  const metricas = (est.metricas || {})[state.grupo] || [];
  const media = state.modo === "media";
  if (!Object.keys(grupos).length) {
    return `<div class="empty">Sem estatísticas nesta temporada.</div>`;
  }
  return `
    <div class="player-stats-head">
      <div class="tabs subtabs" id="jog-grupos" style="margin:0">
        ${Object.entries(grupos)
          .map(
            ([k, lab]) =>
              `<button type="button" class="tab ${state.grupo === k ? "active" : ""}" data-grupo="${k}">${lab}</button>`
          )
          .join("")}
      </div>
      <div class="filters-right" style="display:flex;align-items:center;gap:.75rem;flex-wrap:wrap">
        <span class="player-stats-meta">${est.jogos || 0} jogos · ${est.minutos || 0} min</span>
        <div class="modo-toggle">
          <button type="button" class="chip-btn ${media ? "on" : ""}" data-modo="media">Média</button>
          <button type="button" class="chip-btn ${!media ? "on" : ""}" data-modo="soma">Total</button>
        </div>
      </div>
    </div>
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr><th style="text-align:left">Métrica</th><th>${media ? "Média / jogo" : "Total"}</th></tr>
        </thead>
        <tbody>
          ${metricas
            .map((m) => {
              const v = media ? m.media : m.soma;
              const suf = m.chave === "precisao_chutes" && v != null ? "%" : "";
              return `<tr>
                <td style="text-align:left">${m.label}</td>
                <td><strong>${digStat(m.chave, v)}${suf}</strong></td>
              </tr>`;
            })
            .join("") || `<tr><td colspan="2">Sem dados neste grupo.</td></tr>`}
        </tbody>
      </table>
    </div>`;
}

function tabelaTecnico() {
  const linhas = state.data.linhas || [];
  return `
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr><th>Campeonato</th><th>Clube</th><th>J</th><th>V</th><th>E</th><th>D</th><th>Pts</th></tr>
        </thead>
        <tbody>
          ${linhas
            .map(
              (r) => `<tr>
            <td><a class="camp-link" href="/liga/${r.campeonato_id}">${r.campeonato}</a></td>
            <td><a class="entity-link" href="/clube/${r.clube_id}">${r.clube}</a></td>
            <td>${r.jogos}</td><td>${r.v}</td><td>${r.e}</td><td>${r.d}</td><td><strong>${r.pts}</strong></td>
          </tr>`
            )
            .join("") || `<tr><td colspan="7">Sem dados.</td></tr>`}
        </tbody>
      </table>
    </div>`;
}

function tabelaArbitro() {
  const linhas = state.data.linhas || [];
  return `
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>Campeonato</th><th>Jogos</th><th>Gols</th></tr></thead>
        <tbody>
          ${linhas
            .map(
              (r) => `<tr>
            <td><a class="camp-link" href="/liga/${r.campeonato_id}">${r.campeonato}</a></td>
            <td>${r.jogos}</td><td>${r.gols ?? 0}</td>
          </tr>`
            )
            .join("") || `<tr><td colspan="3">Sem dados.</td></tr>`}
        </tbody>
      </table>
    </div>`;
}

async function render() {
  const e = state.data.entidade || {};
  const titulo =
    tipo === "jogador" ? "Jogador" : tipo === "tecnico" ? "Técnico" : "Árbitro";
  document.title = e.nome || titulo;
  let tabela = "";
  if (tipo === "jogador") tabela = tabelaJogador();
  else if (tipo === "tecnico") tabela = tabelaTecnico();
  else tabela = tabelaArbitro();

  $("#conteudo").innerHTML = `
    <div class="entity-header">
      <div class="entity-photo-wrap">
        ${img(e.foto, "entity-photo")}
        ${pencilBtn("on-photo")}
      </div>
      <div>
        <div class="entity-name-row">
          <h1 class="page-title entity-title">${e.nome || titulo}</h1>
          ${pencilBtn("on-name")}
        </div>
        <p class="muted">${e.posicao || ""} ${e.nacionalidade ? `· ${e.nacionalidade}` : ""} ${e.pais ? `· ${e.pais}` : ""}</p>
      </div>
      <label class="entity-temp season-select">Temporada
        <select id="ent-temp">
          ${(state.data.temporadas || [])
            .map((t) => `<option value="${t}" ${t === state.temporada ? "selected" : ""}>${t}</option>`)
            .join("")}
        </select>
      </label>
    </div>
    <section class="section">
      <h2 class="section-title">Resumo da temporada</h2>
      ${tabela}
    </section>
    ${
      tipo === "jogador"
        ? `<section class="section">
            <h2 class="section-title">Estatísticas</h2>
            ${statsJogador()}
          </section>`
        : ""
    }`;

  setFavicon(e.foto);
  bindEdit();
  $("#ent-temp")?.addEventListener("change", async (ev) => {
    state.temporada = ev.target.value;
    syncUrl();
    await load();
    await render();
  });

  if (tipo === "jogador") {
    $("#jog-grupos")?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-grupo]");
      if (!btn) return;
      state.grupo = btn.dataset.grupo;
      syncUrl();
      render();
    });
    document.querySelectorAll("[data-modo]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.modo = btn.dataset.modo;
        syncUrl();
        render();
      });
    });
  }
}

async function init() {
  const navKey =
    tipo === "jogador" ? "jogadores" : tipo === "tecnico" ? "tecnicos" : tipo === "arbitro" ? "arbitros" : "";
  const navEl = document.querySelector("[data-nav]");
  if (navEl) navEl.dataset.nav = navKey;
  initNav(navKey);
  try {
    await load();
    await render();
  } catch (e) {
    setSiteFavicon();
    $("#conteudo").innerHTML = `<div class="error">${e.message}</div>`;
  }
}

init();
