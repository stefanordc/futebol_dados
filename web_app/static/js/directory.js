import { setSiteFavicon } from "./favicon.js";
import { initNav } from "./nav.js";

const PAGES = {
  jogadores: {
    title: "Jogadores",
    nav: "jogadores",
    text: "Diretório de jogadores em construção. Use a busca ou as estatísticas individuais enquanto isso.",
  },
  tecnicos: {
    title: "Técnicos",
    nav: "tecnicos",
    text: "Diretório de técnicos em construção. Acesse perfis pelos jogos e estatísticas.",
  },
  arbitros: {
    title: "Árbitros",
    nav: "arbitros",
    text: "Diretório de árbitros em construção. Acesse perfis pelos jogos e estatísticas.",
  },
  apostas: {
    title: "Apostas",
    nav: "apostas",
    text: "Mercados de apostas em destaque. Enquanto isso, use Estatísticas → Coletivas → Apostas.",
    cta: { href: "/estatisticas", label: "Ir para Estatísticas → Apostas" },
  },
};

const path = location.pathname.replace(/\/+$/, "").split("/").pop() || "";
const page = PAGES[path] || {
  title: "Diretório",
  nav: "",
  text: "Página não encontrada.",
};

document.title = page.title;
const navEl = document.querySelector("[data-nav]");
if (navEl) navEl.dataset.nav = page.nav;
initNav(page.nav);
setSiteFavicon();

const root = document.getElementById("conteudo");
root.innerHTML = `
  <div class="page-heading hero-heading page-heading-center">
    <h1 class="page-title">${page.title}</h1>
  </div>
  <section class="section directory-placeholder">
    <p class="muted">${page.text}</p>
    ${
      page.cta
        ? `<p><a class="camp-open" href="${page.cta.href}">${page.cta.label}</a></p>`
        : ""
    }
  </section>
`;
