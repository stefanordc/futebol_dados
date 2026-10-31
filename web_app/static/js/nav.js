/** Links do cabeçalho — ativo via data-nav no <nav>. */

export const NAV_LINKS = [
  { href: "/", key: "jogos", label: "Jogos" },
  { href: "/clubes", key: "clubes", label: "Clubes" },
  { href: "/jogadores", key: "jogadores", label: "Jogadores" },
  { href: "/tecnicos", key: "tecnicos", label: "Técnicos" },
  { href: "/arbitros", key: "arbitros", label: "Árbitros" },
  { href: "/estatisticas", key: "estatisticas", label: "Estatísticas" },
  { href: "/apostas", key: "apostas", label: "Apostas" },
];

export function initNav(activeKey = null) {
  const nav = document.querySelector("[data-nav]");
  if (!nav) return;
  const active = activeKey || nav.dataset.nav || "";
  nav.classList.add("top-links");
  nav.innerHTML = NAV_LINKS.map(
    (l) =>
      `<a href="${l.href}" class="${l.key === active ? "active" : ""}">${l.label}</a>`
  ).join("");
}

initNav();
