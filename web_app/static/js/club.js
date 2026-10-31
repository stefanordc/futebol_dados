import { openEditModal, pencilBtn } from "./edit.js";
import { setFavicon, setSiteFavicon } from "./favicon.js";
import { minutosChartsHtml } from "./minutos-charts.js";
import { comportamentoCardsHtml, pctBarsHtml } from "./pct-bars.js";

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

function fmtData(iso) {
  if (!iso) return "—";
  const d = String(iso).slice(0, 10);
  const [y, m, day] = d.split("-");
  if (!y || !m || !day) return d;
  return `${day}/${m}/${y}`;
}

const pathId = Number(location.pathname.split("/").filter(Boolean).pop());
const params = new URLSearchParams(location.search);

let state = {
  data: null,
  aba: params.get("aba") || "geral",
  temporada: params.get("temporada") || null,
  grupo: params.get("grupo") || "ataque",
  compararId: params.get("comparar_id") ? Number(params.get("comparar_id")) : null,
  modo: params.get("modo") === "media" ? "media" : "soma",
  campeonatoId: params.get("campeonato_id") ? Number(params.get("campeonato_id")) : null,
  mando: params.get("mando") || "todos",
};

const INT_METRICAS = new Set([
  "gols",
  "assistencias",
  "faltas_cometidas",
  "dribles_certos",
  "desarmes",
  "interceptacoes",
  "passes_certos",
  "chutes_certos",
  "jogos",
  "v",
  "e",
  "d",
  "gols_marcados",
  "gols_sofridos",
  "saldo",
  "clean_sheets",
  "clean_goals",
  "amarelos",
  "vermelhos",
]);

function fmtValor(chave, v, { media = false } = {}) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const num = Number(v);
  const k = String(chave || "");
  if (k === "gols" || k === "gols_marcados" || k === "gols_sofridos" || k === "gols_contra") {
    if (!media) return n(Math.round(num), 0);
  }
  if (
    chave === "rating" ||
    String(chave).includes("posse") ||
    String(chave).startsWith("pct_") ||
    String(chave).includes("aproveitamento")
  ) {
    return n(num, 2);
  }
  if (media) return n(num, 2);
  if (INT_METRICAS.has(chave) || Math.abs(num - Math.round(num)) < 1e-9) {
    return n(Math.round(num), 0);
  }
  return n(num, 2);
}

function modoToggleHtml() {
  const media = state.modo === "media";
  return `<div class="modo-toggle">
    <button type="button" class="chip-btn ${media ? "on" : ""}" data-modo="media">Média</button>
    <button type="button" class="chip-btn ${!media ? "on" : ""}" data-modo="soma">Total</button>
  </div>`;
}

function syncUrl() {
  const q = new URLSearchParams();
  if (state.temporada) q.set("temporada", state.temporada);
  if (state.aba && state.aba !== "jogos") q.set("aba", state.aba);
  if (state.aba === "estatisticas" && state.grupo) q.set("grupo", state.grupo);
  if (state.compararId) q.set("comparar_id", String(state.compararId));
  if (state.modo === "media") q.set("modo", "media");
  if (state.campeonatoId) q.set("campeonato_id", String(state.campeonatoId));
  if (state.mando && state.mando !== "todos") q.set("mando", state.mando);
  const qs = q.toString();
  history.replaceState(null, "", `/clube/${pathId}${qs ? `?${qs}` : ""}`);
}

async function load() {
  const q = new URLSearchParams({ aba: state.aba });
  if (state.temporada) q.set("temporada", state.temporada);
  if (state.compararId) q.set("comparar_id", String(state.compararId));
  if (state.aba === "estatisticas") q.set("grupo", state.grupo);
  if (state.campeonatoId) q.set("campeonato_id", String(state.campeonatoId));
  if (state.mando && state.mando !== "todos") q.set("mando", state.mando);
  const res = await fetch(`/api/clube/${pathId}?${q.toString().replace(/%2F/gi, "/")}`);
  if (!res.ok) throw new Error("Clube não encontrado");
  state.data = await res.json();
  state.temporada = state.data.temporada;
  state.campeonatoId = state.data.campeonato_id || null;
  state.mando = state.data.mando || "todos";
}

function filtrosClubeHtml() {
  const camps = state.data.campeonatos || [];
  return `
    <div class="clube-toolbar stats-toolbar">
      <label>Campeonato
        <select id="clube-camp">
          <option value="">Todos</option>
          ${camps
            .map(
              (c) =>
                `<option value="${c.id}" ${state.campeonatoId === c.id ? "selected" : ""}>${c.nome}</option>`
            )
            .join("")}
        </select>
      </label>
      <label>Mando de campo
        <select id="clube-mando">
          <option value="todos" ${state.mando === "todos" ? "selected" : ""}>Todos</option>
          <option value="casa" ${state.mando === "casa" ? "selected" : ""}>Casa</option>
          <option value="fora" ${state.mando === "fora" ? "selected" : ""}>Fora</option>
        </select>
      </label>
    </div>`;
}

function headerHtml() {
  const c = state.data.clube || {};
  return `
    <div class="entity-header">
      <div class="entity-photo-wrap">
        ${img(c.logo, "entity-photo")}
        ${pencilBtn("on-photo")}
      </div>
      <div>
        <div class="entity-name-row">
          <h1 class="page-title entity-title">${c.clube || c.nome || "Clube"}</h1>
          ${pencilBtn("on-name")}
        </div>
        <p class="muted">${c.pais || ""}</p>
      </div>
      <label class="entity-temp season-select">Temporada
        <select id="clube-temp">
          ${(state.data.temporadas || [])
            .map((t) => `<option value="${t}" ${t === state.temporada ? "selected" : ""}>${t}</option>`)
            .join("")}
        </select>
      </label>
    </div>
    ${filtrosClubeHtml()}
    <div class="tabs" id="clube-tabs">
      ${[
        ["geral", "Geral"],
        ["jogos", "Jogos"],
        ["estatisticas", "Estatísticas"],
        ["elenco", "Elenco"],
        ["analise", "Análise do Elenco"],
      ]
        .map(
          ([k, lab]) =>
            `<button type="button" class="tab ${state.aba === k ? "active" : ""}" data-aba="${k}">${lab}</button>`
        )
        .join("")}
    </div>`;
}

function renderJogos() {
  const linhas = state.data.jogos?.linhas || [];
  const cols = [
    ["data", "Data"],
    ["temporada", "Temporada"],
    ["campeonato", "Campeonato"],
    ["casa", "Casa"],
    ["gols_casa", "Gols casa"],
    ["gols_fora", "Gols fora"],
    ["fora", "Visitante"],
    ["arbitro", "Árbitro"],
    ["estadio", "Estádio"],
    ["rating_casa", "Rating casa"],
    ["rating_fora", "Rating fora"],
    ["km_casa", "KM Casa"],
    ["km_fora", "KM Fora"],
    ["sprints_casa", "Sprints casa"],
    ["sprints_fora", "Sprints fora"],
  ];
  const cell = (r, k) => {
    if (k === "data") return fmtData(r.data);
    if (k === "campeonato") return r.campeonato || "—";
    if (k === "casa") {
      return `<div class="cell-inner">${img(r.casa_logo)}<span>${r.casa || "—"}</span></div>`;
    }
    if (k === "fora") {
      return `<div class="cell-inner">${img(r.fora_logo)}<span>${r.fora || "—"}</span></div>`;
    }
    if (k === "arbitro") return r.arbitro || "—";
    if (k.startsWith("rating") || k.startsWith("km_")) return n(r[k], 2);
    if (k.startsWith("sprints") || k.startsWith("gols_")) {
      return r[k] == null ? "—" : n(r[k], 0);
    }
    return r[k] ?? "—";
  };
  return `
    <section class="section">
      <h2 class="section-title">Jogos · ${linhas.length}</h2>
      <div class="table-wrap">
        <table class="data-table jogos-clube-table" id="tbl-jogos-clube">
          <thead><tr>${cols.map(([, lab]) => `<th>${lab}</th>`).join("")}</tr></thead>
          <tbody>
            ${
              linhas
                .map(
                  (r) =>
                    `<tr class="jogo-linha" data-jogo="${r.id}" tabindex="0" role="link" title="Abrir jogo">${cols
                      .map(([k]) => `<td>${cell(r, k)}</td>`)
                      .join("")}</tr>`
                )
                .join("") || `<tr><td colspan="${cols.length}">Sem jogos.</td></tr>`
            }
          </tbody>
        </table>
      </div>
    </section>`;
}

function renderGeral() {
  const g = state.data.geral || {};
  const cols = [
    ["campeonato", "Campeonato"],
    ["jogos", "J"],
    ["v", "V"],
    ["e", "E"],
    ["d", "D"],
    ["gols_marcados", "GM"],
    ["gols_sofridos", "GS"],
    ["saldo", "SG"],
    ["aproveitamento", "Aprov. %"],
    ["media_gols_marcados", "Média GM"],
    ["media_gols_sofridos", "Média GS"],
    ["clean_sheets", "CS"],
    ["clean_goals", "CG"],
    ["amarelos", "CA"],
    ["vermelhos", "CV"],
  ];
  const cell = (r, k) => {
    const v = r[k];
    if (k === "campeonato")
      return r.is_total || v === "Total temporada" ? "Total" : (r.campeonato_id ? `<a class="camp-link" href="/liga/${r.campeonato_id}">${v}</a>` : v);
    if (k.includes("media") || k === "aproveitamento") return n(v, 1);
    if (INT_METRICAS.has(k)) return fmtValor(k, v);
    return v ?? "—";
  };
  const row = (r, cls = "") =>
    `<tr class="${cls}">${cols.map(([k]) => `<td>${cell(r, k)}</td>`).join("")}</tr>`;
  return `
    <section class="section">
      <h2 class="section-title">Temporada por campeonato</h2>
      <table class="data-table stats-clube-table">
        <thead><tr>${cols.map(([, lab]) => `<th title="${lab}">${lab}</th>`).join("")}</tr></thead>
        <tbody>
          ${(g.linhas || []).map((r) => row(r)).join("") || `<tr><td colspan="${cols.length}">Sem jogos.</td></tr>`}
        </tbody>
        ${g.total ? `<tfoot class="table-total">${row(g.total, "total-row")}</tfoot>` : ""}
      </table>
    </section>`;
}

function renderElenco() {
  const blocos = state.data.elenco?.blocos || [];
  if (!blocos.length) return `<div class="empty">Sem elenco neste filtro.</div>`;
  return blocos
    .map(
      (b) => `
    <section class="section elenco-bloco">
      <h2 class="section-title">${b.label}</h2>
      <div class="elenco-grid">
        ${(b.itens || [])
          .map((p) => {
            const href = b.chave === "tecnico" ? `/tecnico/${p.id}` : `/jogador/${p.id}`;
            return `<a class="elenco-card" href="${href}">
            ${img(p.foto || p.logo, "elenco-av")}
            <div>
              <strong>${p.nome}</strong>
              <span class="muted">${p.posicao || b.label} · ${p.jogos || 0}J · ${n(p.rating, 1)}</span>
            </div>
          </a>`;
          })
          .join("")}
      </div>
    </section>`
    )
    .join("");
}

function renderAnalise() {
  const tops = state.data.analise?.tops || [];
  if (!tops.length) return `<div class="empty">Sem dados individuais.</div>`;
  const media = state.modo === "media";
  const shortLab = (lab) => {
    const map = {
      Assistências: "Ast",
      Interceptações: "Int",
      "Passes certos": "Passes",
      "Dribles certos": "Dribles",
      "Chutes certos": "Chutes",
    };
    return map[lab] || lab;
  };
  return `
    <div class="filters-row between analise-toolbar">
      <p class="muted" style="margin:0">Top 5 por métrica neste filtro</p>
      ${modoToggleHtml()}
    </div>
    <div class="analise-grid">${tops
      .map((t) => {
        const itens = [...(t.itens || [])]
          .map((p) => {
            const jogos = Number(p.jogos) || 0;
            let display = Number(p.valor);
            if (t.chave !== "rating" && media && jogos > 0) display = display / jogos;
            return { ...p, display };
          })
          .sort((a, b) => (Number(b.display) || 0) - (Number(a.display) || 0))
          .slice(0, 5);
        return `
    <section class="section analise-card">
      <h2 class="section-title">Top 5 — ${t.label}</h2>
      <table class="data-table analise-table">
        <thead><tr><th>#</th><th>Jogador</th><th>${shortLab(t.label)}</th><th>J</th></tr></thead>
        <tbody>
          ${itens
            .map(
              (p, i) => `<tr>
            <td>${i + 1}</td>
            <td class="name-cell"><div class="cell-inner">${img(p.foto)}<a class="entity-link" href="/jogador/${p.id}" title="${p.nome}">${p.nome}</a></div></td>
            <td><strong>${fmtValor(t.chave, p.display, { media: media && t.chave !== "rating" })}</strong></td>
            <td>${p.jogos}</td>
          </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </section>`;
      })
      .join("")}</div>`;
}

function renderComportamento(est) {
  const c = est.comportamento || {};
  return `
    <section class="section">
      <h2 class="section-title">Abertura de placar</h2>
      <p class="muted pct-bars-meta">${c.jogos || 0} jogo${(c.jogos || 0) === 1 ? "" : "s"} no filtro</p>
      ${comportamentoCardsHtml(c.cards)}
    </section>
    ${pctBarsHtml(c.barras, { title: "Mercados e momentos", meta: "" })}`;
}

function renderEstatisticas() {
  const est = state.data.estatisticas || {};
  const mets = est.metricas || [];
  const grupos = est.grupos || state.data.grupos || {};
  const media = state.modo === "media";
  const isMin = state.grupo === "minutos";
  const isComp = state.grupo === "comportamento";
  const cmpNome =
    (est.clubes_opcoes || []).find((c) => c.id === state.compararId)?.clube || "Comparação";
  const nomeClube = state.data.clube?.clube || "Clube";

  let corpo;
  if (isComp) {
    corpo = renderComportamento(est);
  } else if (isMin) {
    corpo = `
      <div class="minutos-clube-grid">
        ${minutosChartsHtml(est.minutos, nomeClube)}
        ${
          est.minutos_comparar
            ? minutosChartsHtml(est.minutos_comparar, cmpNome)
            : ""
        }
      </div>`;
  } else {
    corpo = `
      <table class="data-table stats-clube-table">
        <thead>
          <tr>
            <th>Clube</th><th>J</th>
            ${mets.map((m) => `<th title="${m.label}">${m.label}</th>`).join("")}
          </tr>
        </thead>
        <tbody>
          ${(est.linhas || [])
            .map((r) => {
              const on = r.clube_id === pathId ? "row-on" : "";
              return `<tr class="${on}">
              <td class="name-cell"><div class="cell-inner">${img(r.logo)}<span title="${r.clube}">${r.clube}</span></div></td>
              <td>${r.jogos}</td>
              ${mets
                .map((m) => {
                  const v = (r.valores || {})[m.chave] || {};
                  const val = media ? v.media : v.soma;
                  const suf = String(m.chave).startsWith("pct_") && val != null ? "%" : "";
                  return `<td>${fmtValor(m.chave, val, { media })}${suf}</td>`;
                })
                .join("")}
            </tr>`;
            })
            .join("") || `<tr><td colspan="${2 + mets.length}">Sem dados.</td></tr>`}
        </tbody>
      </table>`;
  }

  return `
    <div class="filters-row between">
      <div class="tabs subtabs" id="clube-grupos">
        ${Object.entries(grupos)
          .map(
            ([k, lab]) =>
              `<button type="button" class="tab ${state.grupo === k ? "active" : ""}" data-grupo="${k}">${lab}</button>`
          )
          .join("")}
      </div>
      <div class="filters-right">
        ${
          isComp
            ? ""
            : `<label class="entity-temp">Comparar com
          <select id="cmp-clube">
            <option value="">—</option>
            ${(est.clubes_opcoes || [])
              .map(
                (c) =>
                  `<option value="${c.id}" ${state.compararId === c.id ? "selected" : ""}>${c.clube}</option>`
              )
              .join("")}
          </select>
        </label>`
        }
        ${isMin || isComp ? "" : modoToggleHtml()}
      </div>
    </div>
    <section class="section stats-clube-section">
      ${corpo}
    </section>`;
}

function bindEdit() {
  const c = state.data.clube;
  document.querySelectorAll(".edit-pencil").forEach((btn) => {
    btn.addEventListener("click", () => {
      openEditModal({
        tipo: "clube",
        id: c.id,
        nome: c.clube || c.nome,
        onSaved: async () => {
          await load();
          await render();
        },
      });
    });
  });
}

function bindFiltrosGlobais() {
  $("#clube-camp")?.addEventListener("change", async (ev) => {
    state.campeonatoId = ev.target.value ? Number(ev.target.value) : null;
    await load();
    await render();
  });
  $("#clube-mando")?.addEventListener("change", async (ev) => {
    state.mando = ev.target.value || "todos";
    await load();
    await render();
  });
}

async function render() {
  const root = $("#conteudo");
  let corpo = "";
  if (state.aba === "jogos") corpo = renderJogos();
  else if (state.aba === "geral") corpo = renderGeral();
  else if (state.aba === "elenco") corpo = renderElenco();
  else if (state.aba === "analise") corpo = renderAnalise();
  else if (state.aba === "estatisticas") corpo = renderEstatisticas();
  else corpo = renderJogos();

  root.innerHTML = `${headerHtml()}<div id="clube-painel">${corpo}</div>`;
  setFavicon(state.data?.clube?.logo || state.data?.clube?.foto);
  syncUrl();
  bindEdit();
  bindFiltrosGlobais();

  $("#clube-temp")?.addEventListener("change", async (ev) => {
    state.temporada = ev.target.value;
    state.campeonatoId = null;
    await load();
    await render();
  });
  $("#clube-tabs")?.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-aba]");
    if (!btn) return;
    state.aba = btn.dataset.aba;
    await load();
    await render();
  });
  $("#clube-grupos")?.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-grupo]");
    if (!btn) return;
    state.grupo = btn.dataset.grupo;
    await load();
    await render();
  });
  $("#cmp-clube")?.addEventListener("change", async (ev) => {
    state.compararId = ev.target.value ? Number(ev.target.value) : null;
    await load();
    await render();
  });
  document.querySelectorAll("[data-modo]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      state.modo = btn.dataset.modo;
      await render();
    });
  });
  document.querySelectorAll("tr.jogo-linha[data-jogo]").forEach((row) => {
    const go = () => {
      const id = row.dataset.jogo;
      if (id) location.href = `/jogo/${id}`;
    };
    row.addEventListener("click", go);
    row.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        go();
      }
    });
  });
}

async function init() {
  try {
    await load();
    document.title = state.data.clube?.clube || "Clube";
    await render();
  } catch (e) {
    setSiteFavicon();
    $("#conteudo").innerHTML = `<div class="error">${e.message}</div>`;
  }
}

init();
