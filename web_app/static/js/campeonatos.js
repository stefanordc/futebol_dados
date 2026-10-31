/* Diretório de campeonatos. Usa somente GET /api/ligas e /liga/{id}. */
(() => {
  'use strict';
  const $ = (selector) => document.querySelector(selector);
  const state = { leagues: [], query: '', country: '', favoritesOnly: false };
  const FAVORITES_KEY = 'ligas_favoritas'; // mesma chave da página Jogos
  const grid = $('#camp-grid');
  const input = $('#camp-search');
  const globalInput = $('#global-search');
  const countrySelect = $('#camp-country');

  function favorites() {
    try {
      const value = JSON.parse(localStorage.getItem(FAVORITES_KEY) || '[]');
      return new Set(Array.isArray(value) ? value.map(Number).filter(Number.isFinite) : []);
    } catch { return new Set(); }
  }

  function saveFavorites(ids) {
    try { localStorage.setItem(FAVORITES_KEY, JSON.stringify([...ids])); }
    catch { window.DF?.toast('Não foi possível salvar favoritos neste navegador.'); }
  }

  function normalized(value) {
    return String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR');
  }

  function imageFor(league) {
    const box = document.createElement('span');
    box.className = 'df-camp-logo';
    const name = String(league.nome || 'Campeonato');
    const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map(word => word[0]).join('').toUpperCase() || 'CF';
    const fallback = () => {
      box.replaceChildren();
      const span = document.createElement('span');
      span.className = 'df-camp-logo-fallback';
      span.textContent = initials;
      span.setAttribute('role', 'img');
      span.setAttribute('aria-label', `Sem logo: ${name}`);
      box.append(span);
    };
    const raw = String(league.logo || '').trim();
    try {
      const url = new URL(raw, location.origin);
      if (!raw || !['http:', 'https:'].includes(url.protocol)) throw new Error('URL inválida');
      const img = document.createElement('img');
      img.src = url.href;
      img.alt = `Logo de ${name}`;
      img.width = 62;
      img.height = 62;
      img.loading = 'lazy';
      img.decoding = 'async';
      img.addEventListener('error', fallback, { once: true });
      box.append(img);
    } catch { fallback(); }
    return box;
  }

  function setActiveButtons() {
    for (const [id, selected] of [['#camp-filter-all', !state.favoritesOnly], ['#camp-filter-favs', state.favoritesOnly]]) {
      const button = $(id);
      button.classList.toggle('active', selected);
      button.setAttribute('aria-pressed', String(selected));
    }
  }

  function makeCard(league, favs) {
    const card = document.createElement('article');
    card.className = 'df-camp-card';
    const main = document.createElement('a');
    main.className = 'df-camp-card-link';
    main.href = `/liga/${encodeURIComponent(league.id)}`;
    main.title = `Abrir ${league.nome}`;
    main.append(imageFor(league));
    const text = document.createElement('div');
    text.className = 'df-camp-card-text';
    const name = document.createElement('h3');
    name.textContent = league.nome;
    const country = document.createElement('p');
    country.textContent = league.pais || 'Competição';
    const count = document.createElement('small');
    const n = Number(league.total_jogos);
    count.textContent = Number.isFinite(n) && n >= 0 ? `${n.toLocaleString('pt-BR')} jogos registrados` : 'Ver campeonato';
    text.append(name, country, count);
    main.append(text);
    const arrow = document.createElement('span');
    arrow.className = 'df-camp-arrow';
    arrow.setAttribute('aria-hidden', 'true');
    arrow.textContent = '›';
    main.append(arrow);

    const star = document.createElement('button');
    star.className = 'df-camp-star';
    star.type = 'button';
    const isFavorite = favs.has(Number(league.id));
    star.classList.toggle('active', isFavorite);
    star.setAttribute('aria-pressed', String(isFavorite));
    star.setAttribute('aria-label', `${isFavorite ? 'Remover dos favoritos' : 'Adicionar aos favoritos'}: ${league.nome}`);
    star.title = isFavorite ? 'Remover dos favoritos' : 'Adicionar aos favoritos';
    star.textContent = isFavorite ? '★' : '☆';
    star.addEventListener('click', () => {
      const next = favorites();
      const id = Number(league.id);
      if (next.has(id)) next.delete(id); else next.add(id);
      saveFavorites(next);
      render();
    });
    card.append(main, star);
    return card;
  }

  function render() {
    setActiveButtons();
    const favs = favorites();
    const term = normalized(state.query.trim());
    const visible = state.leagues.filter(league => {
      if (state.favoritesOnly && !favs.has(Number(league.id))) return false;
      if (state.country && league.pais !== state.country) return false;
      return !term || normalized(`${league.nome} ${league.pais || ''}`).includes(term);
    }).sort((a, b) => {
      const fa = favs.has(Number(a.id));
      const fb = favs.has(Number(b.id));
      if (fa !== fb) return fa ? -1 : 1;
      return String(a.nome).localeCompare(String(b.nome), 'pt-BR', { sensitivity: 'base' });
    });
    $('#camp-total').textContent = `${state.leagues.length.toLocaleString('pt-BR')} campeonatos`;
    $('#camp-visible').textContent = `${visible.length.toLocaleString('pt-BR')} resultado${visible.length === 1 ? '' : 's'}`;
    const frag = document.createDocumentFragment();
    if (!visible.length) {
      const empty = document.createElement('div');
      empty.className = 'df-empty df-camp-empty';
      const title = document.createElement('h3');
      title.textContent = 'Nenhum campeonato encontrado';
      const detail = document.createElement('p');
      detail.textContent = 'Tente outro nome, país ou filtro de favoritos.';
      const clear = document.createElement('button');
      clear.type = 'button';
      clear.className = 'df-primary-btn';
      clear.textContent = 'Limpar filtros';
      clear.addEventListener('click', () => {
        state.query = ''; state.country = ''; state.favoritesOnly = false;
        input.value = ''; if (globalInput) globalInput.value = '';
        countrySelect.value = '';
        render();
      });
      empty.append(title, detail, clear);
      frag.append(empty);
    } else {
      for (const league of visible) frag.append(makeCard(league, favs));
    }
    grid.replaceChildren(frag);
  }

  function setQuery(value, origin) {
    state.query = value;
    if (origin !== input) input.value = value;
    if (globalInput && origin !== globalInput) globalInput.value = value;
    render();
  }
  input.addEventListener('input', () => setQuery(input.value, input));
  globalInput?.addEventListener('input', () => setQuery(globalInput.value, globalInput));
  $('#camp-filter-all').addEventListener('click', () => { state.favoritesOnly = false; render(); });
  $('#camp-filter-favs').addEventListener('click', () => { state.favoritesOnly = true; render(); });
  countrySelect.addEventListener('change', () => { state.country = countrySelect.value; render(); });

  async function load() {
    try {
      const res = await fetch('/api/ligas', { headers: { Accept: 'application/json' } });
      if (!res.ok) throw new Error(`Falha na consulta (HTTP ${res.status})`);
      const data = await res.json();
      if (!Array.isArray(data.ligas)) throw new Error('Formato de resposta inesperado');
      state.leagues = data.ligas.filter(x => x && Number.isFinite(Number(x.id)) && typeof x.nome === 'string' && x.nome.trim());
      const countries = [...new Set(state.leagues.map(x => x.pais).filter(Boolean))].sort((a,b) => String(a).localeCompare(String(b),'pt-BR'));
      countrySelect.replaceChildren(new Option('Todos os países', ''));
      for (const country of countries) countrySelect.add(new Option(country, country));
      render();
    } catch (error) {
      $('#camp-total').textContent = 'Indisponível';
      $('#camp-visible').textContent = '';
      grid.innerHTML = '';
      const panel = document.createElement('div');
      panel.className = 'df-error df-camp-empty';
      const title = document.createElement('h3');
      title.textContent = 'Não foi possível carregar os campeonatos';
      const p = document.createElement('p');
      p.textContent = error.message;
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.className = 'df-primary-btn';
      retry.textContent = 'Tentar novamente';
      retry.addEventListener('click', () => { grid.innerHTML = '<div class="df-camp-skeleton"></div><div class="df-camp-skeleton"></div>'; load(); });
      panel.append(title, p, retry);
      grid.append(panel);
    }
  }
  load();
})();
