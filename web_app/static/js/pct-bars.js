/** Barras de percentual com autopreenchimento. */

export function pctBarsHtml(barras, { title = "", meta = "" } = {}) {
  const rows = (barras || [])
    .map((b) => {
      const pct = Math.max(0, Math.min(100, Number(b.pct) || 0));
      return `<div class="pct-bar-row" title="${b.n ?? 0} em ${(b.total != null ? b.total : "") || "jogos"}">
        <span class="pct-bar-lab">${b.label}</span>
        <div class="pct-bar-track"><div class="pct-bar-fill" style="width:${pct}%"></div></div>
        <span class="pct-bar-val">${pct.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%</span>
      </div>`;
    })
    .join("");
  return `
    <section class="section pct-bars-card">
      ${title ? `<h2 class="section-title">${title}</h2>` : ""}
      ${meta ? `<p class="muted pct-bars-meta">${meta}</p>` : ""}
      <div class="pct-bars">${rows || `<div class="empty">Sem dados.</div>`}</div>
    </section>`;
}

export function comportamentoCardsHtml(cards) {
  const itens = (cards || [])
    .map(
      (c) => `<article class="comp-card">
        <strong class="comp-card-pct">${(Number(c.pct) || 0).toLocaleString("pt-BR", {
          maximumFractionDigits: 1,
        })}%</strong>
        <span class="comp-card-lab">${c.label}</span>
        <span class="comp-card-n muted">${c.n ?? 0} jogos</span>
      </article>`
    )
    .join("");
  return `<div class="comp-cards">${itens || `<div class="empty">Sem dados.</div>`}</div>`;
}
