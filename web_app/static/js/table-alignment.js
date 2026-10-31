/** Separa escudos/fotos e nomes em colunas próprias nas tabelas de todo o site.
 * Mantém links, ordenação, navegação e scripts originais do backend intactos.
 */
(() => {
  'use strict';
  if (window.__dfTableAlignment) return;
  window.__dfTableAlignment = true;
  const tables = '.data-table, .analise-table, .stats-clube-table';
  const escape = value => String(value || '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

  function convert(table) {
    if (table.dataset.dfImageAligned === 'true') return;
    const head = table.tHead?.rows?.[0];
    const tbody = table.tBodies?.[0];
    if (!head || !tbody) return;
    const rows = [...tbody.rows];
    if (!rows.length) return;
    const sample = rows.slice(0, 30).filter(row => ![...row.cells].some(cell => cell.colSpan > 1));
    if (!sample.length) return;
    const originalColumns = head.cells.length;
    // Uma coluna só é separada quando contém identidade (imagem + nome), nunca fotos de gráficos.
    const ids = [];
    for (let i = 0; i < originalColumns; i++) {
      if (sample.some(row => {
        const cell = row.cells[i];
        const inner = cell?.querySelector(':scope > .cell-inner');
        if (!inner) return false;
        return Boolean(inner.querySelector(':scope > img, :scope > .mini-av, :scope > .club-tile-fallback') ||
          (inner.querySelector(':scope > a, :scope > span') && sample.some(other => other.cells[i]?.querySelector(':scope > .cell-inner > img'))));
      })) ids.push(i);
    }
    if (!ids.length) return;
    for (const idx of ids.reverse()) {
      const header = head.cells[idx];
      if (!header) continue;
      const imgHead = document.createElement('th');
      imgHead.className = 'df-image-column df-image-heading';
      imgHead.scope = 'col';
      imgHead.textContent = 'IMG';
      imgHead.title = 'Escudo ou foto';
      header.before(imgHead);
      header.classList.add('df-name-column');
      rows.forEach(row => {
        const cell = row.cells[idx];
        if (!cell || cell.colSpan > 1 || cell.tagName !== 'TD') return;
        const inner = cell.querySelector(':scope > .cell-inner');
        const newCell = document.createElement('td');
        newCell.className = 'df-image-column';
        if (inner) {
          const image = inner.querySelector(':scope > img, :scope > .mini-av');
          if (image) {
            const holder = document.createElement('span');
            holder.className = 'df-image-holder';
            image.before(holder);
            holder.appendChild(image);
            newCell.appendChild(holder);
            image.classList.add('df-image-element');
            image.loading = 'lazy';
          } else {
            const label = inner.textContent?.trim() || '';
            newCell.innerHTML = `<span class="df-image-fallback" aria-hidden="true">${escape(label.slice(0,1).toUpperCase() || '—')}</span>`;
          }
        }
        cell.classList.add('df-name-column');
        cell.before(newCell);
      });
    }
    table.dataset.dfImageAligned = 'true';
  }

  function update() {
    document.querySelectorAll(tables).forEach(convert);
  }
  let pending = false;
  const obs = new MutationObserver(() => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; update(); });
  });
  obs.observe(document.documentElement, {childList:true, subtree:true});
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', update);
  else update();
})();
