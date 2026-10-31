const $ = (sel, el = document) => el.querySelector(sel);

const FAV_KEY = "ligas_favoritas";

function fmtData(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}`;
}

function logo(src, alt) {
  if (!src) return `<span style="width:20px;height:20px;display:inline-block"></span>`;
  return `<img src="${src}" alt="${alt || ""}" loading="lazy" onerror="this.style.opacity=0.2" />`;
}

function getFavoritos() {
  try {
    const raw = JSON.parse(localStorage.getItem(FAV_KEY) || "[]");
    return Array.isArray(raw) ? raw.map(Number).filter((n) => !Number.isNaN(n)) : [];
  } catch {
    return [];
  }
}

function setFavoritos(ids) {
  localStorage.setItem(FAV_KEY, JSON.stringify([...new Set(ids)]));
}

function toggleFavorito(id) {
  const favs = getFavoritos();
  const i = favs.indexOf(id);
  if (i >= 0) favs.splice(i, 1);
  else favs.push(id);
  setFavoritos(favs);
  return favs;
}

function ordenarLigas(ligas) {
  const favSet = new Set(getFavoritos());
  const alpha = (a, b) => (a.nome || "").localeCompare(b.nome || "", "pt", { sensitivity: "base" });
  const favs = ligas.filter((l) => favSet.has(l.id)).sort(alpha);
  const resto = ligas.filter((l) => !favSet.has(l.id)).sort(alpha);
  return [...favs, ...resto];
}

let cacheLigas = [];
let ligaAtiva = null;

function renderLigas(ligas, ativo) {
  const box = $("#lista-ligas");
  if (!ligas.length) {
    box.innerHTML = `<div class="empty">Nenhuma liga com jogos no banco.</div>`;
    return;
  }
  const favSet = new Set(getFavoritos());
  const ordenadas = ordenarLigas(ligas);

  box.innerHTML = [
    `<button class="liga-item ${ativo == null ? "active" : ""}" data-id="" type="button">
      <span>Todas</span>
    </button>`,
    ...ordenadas.map((l) => {
      const fav = favSet.has(l.id);
      return `<div class="liga-item ${ativo === l.id ? "active" : ""}" data-id="${l.id}">
        <button class="liga-select" type="button" data-id="${l.id}">
          ${logo(l.logo, l.nome)}
          <span>${l.nome}</span>
        </button>
        <button class="star-btn ${fav ? "on" : ""}" type="button" data-star="${l.id}"
          title="${fav ? "Remover dos favoritos" : "Favoritar"}" aria-label="Favoritar">
          ${fav ? "★" : "☆"}
        </button>
      </div>`;
    }),
  ].join("");

  box.querySelector(".liga-item[data-id='']")?.addEventListener("click", () => {
    ligaAtiva = null;
    carregarJogos(null);
    renderLigas(cacheLigas, null);
  });

  box.querySelectorAll(".liga-select").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = Number(btn.dataset.id);
      if (id) location.href = `/liga/${id}`;
    });
  });

  box.querySelectorAll(".star-btn").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const id = Number(btn.dataset.star);
      toggleFavorito(id);
      renderLigas(cacheLigas, ligaAtiva);
    });
  });
}

function renderFeed(grupos, termo = "") {
  const feed = $("#feed");
  const t = termo.trim().toLowerCase();
  const filtrados = grupos
    .map((g) => ({
      ...g,
      jogos: g.jogos.filter((j) => {
        if (!t) return true;
        const blob = `${g.campeonato} ${g.pais} ${j.casa} ${j.fora}`.toLowerCase();
        return blob.includes(t);
      }),
    }))
    .filter((g) => g.jogos.length);

  if (!filtrados.length) {
    feed.innerHTML = `<div class="empty">Nenhum jogo da última rodada encontrado.</div>`;
    return;
  }

  feed.innerHTML = filtrados
    .map(
      (g) => `
    <article class="liga-block">
      <div class="liga-block-head">
        ${logo(g.logo, g.campeonato)}
        <span>${g.pais ? `${g.pais} — ` : ""}${g.campeonato}</span>
        <span class="pais" style="margin-left:auto">${g.jogos[0]?.rodada || "Última rodada"}</span>
      </div>
      ${g.jogos
        .map(
          (j) => `
        <div class="jogo-row" role="link" tabindex="0" data-jogo="/jogo/${j.id}">
          <div class="jogo-status">
            <div class="fj">FJ</div>
            <div>${fmtData(j.data)}</div>
          </div>
          <div class="times">
            <div class="time">${logo(j.casa_logo, j.casa)}${j.casa_id ? `<a class="entity-link" href="/clube/${j.casa_id}">${j.casa}</a>` : `<span>${j.casa}</span>`}</div>
            <div class="time">${logo(j.fora_logo, j.fora)}${j.fora_id ? `<a class="entity-link" href="/clube/${j.fora_id}">${j.fora}</a>` : `<span>${j.fora}</span>`}</div>
          </div>
          <div>
            <div class="placar">
              <div>${j.gols_casa ?? "-"}</div>
              <div>${j.gols_fora ?? "-"}</div>
            </div>
            <div class="rodada-tag">${j.rodada || ""}</div>
          </div>
        </div>`
        )
        .join("")}
    </article>`
    )
    .join("");

  feed.querySelectorAll(".jogo-row[data-jogo]").forEach((row) => {
    const go = () => {
      location.href = row.dataset.jogo;
    };
    row.addEventListener("click", (ev) => {
      if (ev.target.closest("a")) return;
      go();
    });
    row.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        if (ev.target.closest("a")) return;
        go();
      }
    });
  });
}

let cacheGrupos = [];

async function carregarLigas() {
  const res = await fetch("/api/ligas");
  if (!res.ok) throw new Error("Falha ao carregar ligas");
  const data = await res.json();
  cacheLigas = data.ligas || [];
  renderLigas(cacheLigas, ligaAtiva);
}

async function carregarJogos(campeonatoId = null) {
  const feed = $("#feed");
  feed.innerHTML = `<div class="loading">Carregando jogos…</div>`;
  const qs = new URLSearchParams({ limite: "200" });
  if (campeonatoId) qs.set("campeonato_id", String(campeonatoId));
  const res = await fetch(`/api/jogos?${qs}`);
  if (!res.ok) throw new Error("Falha ao carregar jogos");
  const data = await res.json();
  cacheGrupos = data.grupos || [];
  renderFeed(cacheGrupos, $("#busca").value);
}

async function init() {
  try {
    await Promise.all([carregarLigas(), carregarJogos()]);
  } catch (e) {
    $("#feed").innerHTML = `<div class="error">${e.message}</div>`;
    $("#lista-ligas").innerHTML = `<div class="error">Erro ao conectar no banco.</div>`;
  }
  $("#busca").addEventListener("input", (ev) => renderFeed(cacheGrupos, ev.target.value));
}

init();
