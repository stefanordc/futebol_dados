/** Favicon padrão do site (bola / logo). */
export const SITE_FAVICON = "/static/img/favicon.png";

function applyHref(href) {
  let link = document.querySelector('link[rel="icon"]');
  if (!link) {
    link = document.createElement("link");
    link.rel = "icon";
    document.head.appendChild(link);
  }
  const isData = href.startsWith("data:");
  link.type = href.includes(".svg") ? "image/svg+xml" : "image/png";
  // cache-bust para trocar o ícone ao mudar de página/entidade
  link.href = isData ? href : `${href}${href.includes("?") ? "&" : "?"}fav=${Date.now()}`;

  let apple = document.querySelector('link[rel="apple-touch-icon"]');
  if (!apple) {
    apple = document.createElement("link");
    apple.rel = "apple-touch-icon";
    document.head.appendChild(apple);
  }
  apple.href = link.href;
}

/**
 * Atualiza o ícone da aba do navegador.
 * @param {string|null|undefined} url Foto/logo da entidade; se vazio ou falhar, usa a logo do site.
 */
export function setFavicon(url) {
  const href = (url && String(url).trim()) || "";
  if (!href) {
    applyHref(SITE_FAVICON);
    return;
  }
  const probe = new Image();
  probe.onload = () => applyHref(href);
  probe.onerror = () => applyHref(SITE_FAVICON);
  probe.src = href;
}

export function setSiteFavicon() {
  applyHref(SITE_FAVICON);
}
