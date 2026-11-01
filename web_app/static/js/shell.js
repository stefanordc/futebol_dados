/* Dados Futebol — shell frontend. Nenhum endpoint alterado. */
(() => {
  'use strict';
  if (window.__dfShell) return;
  window.__dfShell = true;
  const links = [
    ['Jogos', '/', 'calendar'], ['Campeonatos', '/static/campeonatos.html', 'trophy'], ['Clubes', '/clubes', 'shield'],
    ['Jogadores', '/jogadores', 'users'], ['Técnicos', '/tecnicos', 'briefcase'],
    ['Árbitros', '/arbitros', 'flag'], ['Estatísticas', '/estatisticas', 'chart'],
    ['Apostas', '/apostas', 'trending']
  ];
  const strokes = {
    trophy:'<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4ZM7 6H4v2a4 4 0 0 0 4 4M17 6h3v2a4 4 0 0 1-4 4"/>',
    calendar:'<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M8 2v4M16 2v4M3 10h18M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01"/>',
    shield:'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/>',
    users:'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    briefcase:'<rect x="3" y="7" width="18" height="14" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18M10 12v2h4v-2"/>',
    flag:'<path d="M4 22V4M4 5c4-3 8 3 12 0v12c-4 3-8-3-12 0"/>',
    chart:'<path d="M3 3v18h18M7 16l4-4 3 2 6-7"/>',
    trending:'<path d="m3 17 6-6 4 4 8-8M15 7h6v6"/>',
    sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon:'<path d="M20.9 13a9 9 0 0 1-9.9-9.9A9 9 0 1 0 20.9 13Z"/>',
    pin:'<path d="m16 3 5 5-3 1-3 3-1 8-2-2-3-3-4 6M7 7l4 4"/>',
    menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
    search:'<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4"/>',
    x:'<path d="M18 6 6 18M6 6l12 12"/>',
    arrow:'<path d="M5 12h14M12 5l7 7-7 7"/>',
    info:'<circle cx="12" cy="12" r="10"/><path d="M12 11v6M12 7h.01"/>',
    star:'<path d="m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.9L12 17.8l-6.2 3.3L7 14.2 2 9.3l6.9-1Z"/>',
    chevron:'<path d="m6 9 6 6 6-6"/>'
  };
  function icon(name, size = 20) {
    return `<svg aria-hidden="true" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${strokes[name] || strokes.info}</svg>`;
  }
  const get = (key, fallback='') => { try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; } };
  const set = (key, value) => { try { localStorage.setItem(key, value); } catch {} };
  const theme = () => document.documentElement.getAttribute('data-theme') || 'dark';
  function changeTheme(value) {
    document.documentElement.setAttribute('data-theme', value);
    set('df_theme', value);
    const btn = document.getElementById('df-theme-btn');
    if (btn) { btn.innerHTML = icon(value === 'dark' ? 'sun' : 'moon'); btn.title = value === 'dark' ? 'Usar tema claro' : 'Usar tema escuro'; btn.setAttribute('aria-label', btn.title); }
    document.dispatchEvent(new CustomEvent('df:theme', { detail: { theme: value } }));
  }
  const path = location.pathname;
  const active = path === '/' || path.startsWith('/jogo/') || path.startsWith('/liga/') ? '/' :
    path.startsWith('/clube/') ? '/clubes' :
    path.startsWith('/jogador/') ? '/jogadores' :
    path.startsWith('/tecnico/') ? '/tecnicos' :
    path.startsWith('/arbitro/') ? '/arbitros' :
    path.startsWith('/apostas/') ? '/apostas' : links.find(x => x[1] === path)?.[1] || '/';
  const activeTitle = links.find(x => x[1] === active)?.[0] || 'Jogos';
  const sideMount = document.getElementById('df-sidebar-mount');
  const topMount = document.getElementById('df-topbar-mount');
  if (!sideMount || !topMount) return;
  sideMount.innerHTML = `<div class="df-mobile-backdrop" id="df-backdrop" hidden></div><aside class="df-sidebar-nav" id="df-sidebar" aria-label="Navegação principal">
    <a href="/" class="df-brand" aria-label="Dados Futebol — início"><span class="df-brand-icon">DF</span><span class="df-brand-label">DADOS<span>FUTEBOL</span></span></a>
    <div class="df-side-caption">MENU</div>
    <nav class="df-nav-list" aria-label="Páginas">${links.map(([label, href, glyph]) => `<a href="${href}" class="df-nav-item ${active===href?'active':''}" title="${label}" ${active===href?'aria-current="page"':''}>${icon(glyph,22)}<span class="df-nav-name">${label}</span></a>`).join('')}</nav>
    <div class="df-sidebar-bottom"><button id="df-pin" class="df-nav-item df-pin-btn" type="button" title="Fixar a navegação" aria-pressed="false">${icon('pin',20)}<span class="df-nav-name">Fixar menu</span></button><div class="df-product-note">ESTATÍSTICAS · DADOS FUTEBOL</div></div>
  </aside>`;
  topMount.className = 'df-topbar';
  topMount.innerHTML = `<div class="df-topbar-left"><button class="df-icon-button df-hamburger" id="df-menu" type="button" aria-label="Abrir menu" aria-expanded="false">${icon('menu')}</button><div class="df-topbar-heading"><div class="df-topbar-page">${activeTitle}</div><div class="df-topbar-subtitle">Seu painel de futebol</div></div></div>
  <div class="df-topbar-actions"><label class="df-global-search">${icon('search',19)}<input id="${active === '/'?'busca':'global-search'}" type="search" placeholder="${path === '/static/campeonatos.html' ? 'Buscar campeonato...' : 'Buscar clube ou liga...'}" autocomplete="off" aria-label="Buscar clube ou liga"><span class="df-keyboard-shortcut">Ctrl K</span></label><button class="df-icon-button" id="df-theme-btn" type="button" title="Alternar tema" aria-label="Alternar tema">${icon(theme()==='dark'?'sun':'moon')}</button><button class="df-icon-button df-notif-btn" id="df-notifications" type="button" aria-label="Informações do painel" aria-expanded="false">${icon('bell')}</button><span class="df-account-avatar" title="Dados Futebol" aria-label="Dados Futebol">DF</span></div>
  <div id="df-notice-popover" class="df-popover" role="status" hidden><strong>Sobre os dados</strong><p>Os resultados exibidos vêm das últimas rodadas registradas no banco. Não há atualização ao vivo nesta versão.</p></div>`;
  const side = document.getElementById('df-sidebar');
  const menuBtn = document.getElementById('df-menu');
  const backdrop = document.getElementById('df-backdrop');
  const pinBtn = document.getElementById('df-pin');
  const fixed = get('df_sidebar_pinned') === 'true';
  function syncPin(pinned) {
    document.body.classList.toggle('df-pinned', pinned);
    pinBtn.setAttribute('aria-pressed', String(pinned));
    pinBtn.title = pinned ? 'Desafixar navegação' : 'Fixar navegação';
    pinBtn.querySelector('.df-nav-name').textContent = pinned ? 'Desafixar menu' : 'Fixar menu';
  }
  syncPin(fixed);
  pinBtn.addEventListener('click', () => { const next = !document.body.classList.contains('df-pinned'); syncPin(next); set('df_sidebar_pinned',String(next)); });
  let hoverTimeout;
  side.addEventListener('mouseenter', () => { clearTimeout(hoverTimeout); if (window.innerWidth >= 768) side.classList.add('df-hovered'); });
  side.addEventListener('mouseleave', () => { clearTimeout(hoverTimeout); hoverTimeout = setTimeout(() => side.classList.remove('df-hovered'), 210); });
  function toggleDrawer(force) {
    const open = typeof force === 'boolean' ? force : !side.classList.contains('df-mobile-open');
    side.classList.toggle('df-mobile-open', open);
    backdrop.hidden = !open;
    menuBtn.setAttribute('aria-expanded', String(open));
    menuBtn.setAttribute('aria-label', open ? 'Fechar menu' : 'Abrir menu');
    document.body.classList.toggle('df-drawer-open', open);
    if (open) side.querySelector('.df-nav-item')?.focus(); else menuBtn.focus();
  }
  menuBtn.addEventListener('click', () => toggleDrawer());
  backdrop.addEventListener('click', () => toggleDrawer(false));
  window.addEventListener('resize', () => { if (window.innerWidth >= 768 && side.classList.contains('df-mobile-open')) toggleDrawer(false); });
  const input = topMount.querySelector('input[type=search]');
  window.addEventListener('keydown', ev => {
    const tag = document.activeElement?.tagName;
    const editable = ['INPUT','SELECT','TEXTAREA'].includes(tag) || document.activeElement?.isContentEditable;
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'k') { ev.preventDefault(); input.focus(); input.select(); }
    else if (ev.key === '/' && !editable && !ev.ctrlKey && !ev.metaKey && !ev.altKey) { ev.preventDefault(); input.focus(); }
    if (ev.key === 'Escape') { if (side.classList.contains('df-mobile-open')) toggleDrawer(false); document.getElementById('df-notice-popover').hidden = true; }
  });
  if (path !== '/' && path !== '/static/campeonatos.html') {
    input.addEventListener('keydown', ev => {
      if (ev.key !== 'Enter') return;
      ev.preventDefault();
      const q = input.value.trim();
      if (q) location.assign('/?busca=' + encodeURIComponent(q));
    });
  }
  document.getElementById('df-theme-btn').addEventListener('click', () => changeTheme(theme()==='dark'?'light':'dark'));
  const notify = document.getElementById('df-notifications');
  notify.addEventListener('click', () => {
    const popup = document.getElementById('df-notice-popover');
    popup.hidden = !popup.hidden;
    notify.setAttribute('aria-expanded', String(!popup.hidden));
  });
  // Regra principal: aprimorar conteúdo gerado pela aplicação sem substituir eventos ou mudar contratos.
  function enhanceImages(node) {
    const images = node.querySelectorAll ? node.querySelectorAll('img:not([data-df-improved])') : [];
    images.forEach(img => {
      img.dataset.dfImproved = '1';
      img.loading = img.loading || 'lazy';
      img.addEventListener('error', () => {
        if (!img.isConnected || img.dataset.dfError) return;
        img.dataset.dfError = '1';
        const alt = (img.getAttribute('alt') || img.parentElement?.textContent || 'DF').trim();
        const label = alt.split(/\s+/).slice(0,2).map(x => x[0]||'').join('').toUpperCase().slice(0,2) || 'DF';
        const span = document.createElement('span'); span.className = 'df-img-fallback'; span.textContent = label;
        span.setAttribute('role','img'); span.setAttribute('aria-label',alt||'Escudo indisponível');
        img.replaceWith(span);
      }, {once:true});
    });
  }
  function enhanceContent(root) {
    enhanceImages(root);
    root.querySelectorAll?.('.loading:not([data-df-skeleton])').forEach(e => {e.dataset.dfSkeleton='1';e.classList.add('df-loading-state');});
    root.querySelectorAll?.('.data-table:not([data-df-accessible])').forEach(table => {
      table.dataset.dfAccessible='1';
      table.querySelectorAll('th.sortable').forEach(th => { if(!th.hasAttribute('tabindex'))th.tabIndex=0; });
    });
  }
  enhanceContent(document);
  let scheduled = false;
  new MutationObserver(() => {
    if(scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled=false; enhanceContent(document.getElementById('main-content') || document); });
  }).observe(document.getElementById('main-content'), {childList:true, subtree:true});
  window.DF = {
    icon, changeTheme, escape: value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
    toast(message) {
      const root = document.getElementById('df-toast');
      const item = document.createElement('div'); item.className='df-toast'; item.textContent=String(message);
      root.appendChild(item); setTimeout(()=>item.remove(),4000);
    }
  };
  if (path === '/apostas' || path.startsWith('/apostas/')) {
    const footer = document.createElement('footer');footer.className='df-responsible';footer.textContent='Apostas envolvem riscos financeiros. Defina limites e aposte com responsabilidade. Proibido para menores de 18 anos.';
    document.querySelector('main')?.appendChild(footer);
  }
})();
