/** Gráficos da aba Minutos — visão em camadas (15' → 5'). */

const INTERVALOS_15 = [
  { key: "0-15", label: "0–15", from: 1, to: 15 },
  { key: "16-30", label: "16–30", from: 16, to: 30 },
  { key: "31-45", label: "31–45", from: 31, to: 45 },
  { key: "46-60", label: "46–60", from: 46, to: 60 },
  { key: "61-75", label: "61–75", from: 61, to: 75 },
  { key: "76-90", label: "76–90", from: 76, to: 89 },
  { key: "90+", label: "90+", plus: true },
];

/** 0–5, 6–10, …, 86–90 + 90+ */
const INTERVALOS_5 = (() => {
  const list = [];
  for (let start = 0; start < 90; start += 5) {
    const from = start === 0 ? 1 : start + 1;
    const to = start + 5;
    list.push({
      key: `${start}-${to}`,
      label: `${start}–${to}`,
      from,
      to: Math.min(to, 89),
    });
  }
  list.push({ key: "90+", label: "90+", plus: true });
  return list;
})();

function buildSerie(golsPorMinuto) {
  const map = new Map();
  let plus = 0;
  for (const g of golsPorMinuto || []) {
    if (g.label === "90+") {
      plus = Number(g.gols) || 0;
    } else {
      const m = Number(g.minuto);
      if (m >= 1 && m <= 89) map.set(m, Number(g.gols) || 0);
    }
  }
  const serie = [];
  for (let m = 1; m <= 89; m++) serie.push({ minuto: m, gols: map.get(m) || 0 });
  serie.push({ minuto: 90, label: "90+", gols: plus });
  return serie;
}

function agregar(serie, defs) {
  const byMin = new Map(serie.map((g) => [g.minuto, g.gols]));
  const plus = serie.find((g) => g.label === "90+")?.gols || 0;
  return defs.map((iv) => {
    if (iv.plus) return { ...iv, gols: plus };
    let total = 0;
    for (let m = iv.from; m <= iv.to; m++) total += byMin.get(m) || 0;
    return { ...iv, gols: total };
  });
}

function cardPlacar(st, meta) {
  return `
    <section class="min-panel">
      <header class="min-panel-head">
        <div>
          <h3 class="min-panel-title">Tempo de placar</h3>
          <p class="min-panel-sub">${meta}</p>
        </div>
      </header>
      <div class="estado-bar estado-bar-lg" title="Vencendo / Empatando / Perdendo">
        <div class="estado-seg vencendo" style="width:${st.vencendo || 0}%">${st.vencendo >= 8 ? `${st.vencendo}%` : ""}</div>
        <div class="estado-seg empatando" style="width:${st.empatando || 0}%">${st.empatando >= 8 ? `${st.empatando}%` : ""}</div>
        <div class="estado-seg perdendo" style="width:${st.perdendo || 0}%">${st.perdendo >= 8 ? `${st.perdendo}%` : ""}</div>
      </div>
      <div class="estado-stats">
        <div class="estado-stat">
          <span class="dot vencendo"></span>
          <div>
            <strong>${st.vencendo || 0}%</strong>
            <small>Vencendo · ${st.minutos_vencendo ?? "—"} min</small>
          </div>
        </div>
        <div class="estado-stat">
          <span class="dot empatando"></span>
          <div>
            <strong>${st.empatando || 0}%</strong>
            <small>Empatando · ${st.minutos_empatando ?? "—"} min</small>
          </div>
        </div>
        <div class="estado-stat">
          <span class="dot perdendo"></span>
          <div>
            <strong>${st.perdendo || 0}%</strong>
            <small>Perdendo · ${st.minutos_perdendo ?? "—"} min</small>
          </div>
        </div>
      </div>
    </section>`;
}

function cardIntervalos(intervalos, meta, { title, subtitle, dense = false }) {
  const maxG = Math.max(1, ...intervalos.map((i) => i.gols));
  const cols = intervalos
    .map((iv) => {
      const h = Math.round((100 * iv.gols) / maxG);
      return `<div class="int-col" title="${iv.label} · ${iv.gols} gol(s)">
        <span class="int-val">${iv.gols}</span>
        <div class="int-track"><div class="int-fill" style="height:${iv.gols ? Math.max(h, 4) : 0}%"></div></div>
        <span class="int-lab">${iv.label}</span>
      </div>`;
    })
    .join("");
  return `
    <section class="min-panel">
      <header class="min-panel-head">
        <div>
          <h3 class="min-panel-title">${title}</h3>
          <p class="min-panel-sub">${subtitle || meta}</p>
        </div>
      </header>
      <div class="int-cols ${dense ? "int-cols-5" : ""}">${cols}</div>
    </section>`;
}

/**
 * @param {object|null} minutos
 * @param {string} titulo
 */
export function minutosChartsHtml(minutos, titulo) {
  if (!minutos) {
    return `<div class="min-panel"><p class="fin-hint">Sem dados de minutos para este clube.</p></div>`;
  }
  const meta = `${titulo || "Clube"} · ${minutos.jogos || 0} jogo(s)`;
  const st = minutos.estado || {};
  const serie = buildSerie(minutos.gols_por_minuto);
  const iv15 = agregar(serie, INTERVALOS_15);
  const iv5 = agregar(serie, INTERVALOS_5);

  return `
    <div class="minutos-dashboard">
      ${cardPlacar(st, meta)}
      ${cardIntervalos(iv15, meta, {
        title: "Gols por intervalo",
        subtitle: `${meta} · faixas de 15 minutos`,
      })}
      ${cardIntervalos(iv5, meta, {
        title: "Gols a cada 5 minutos",
        subtitle: `${meta} · 0–5, 6–10, …, 86–90 e acréscimos`,
        dense: true,
      })}
    </div>`;
}
