/* Página Jogos — usa EXCLUSIVAMENTE /api/ligas, /api/jogos e /api/jogo/{id} existentes. */
const $ = (sel, root=document) => root.querySelector(sel);
const $$ = (sel, root=document) => [...root.querySelectorAll(sel)];
const safe = window.DF?.escape || (s=>String(s??''));
const icon = window.DF?.icon || (()=>'');
const LEAGUE_KEY = 'ligas_favoritas'; // mesmo contrato de favoritos do home.js original
const MATCH_KEY = 'df_fav_matches';
function storageRead(key) { try { const value=JSON.parse(localStorage.getItem(key)||'[]'); return Array.isArray(value) ? value.map(Number).filter(Number.isFinite) : []; }catch{return [];} }
function storageWrite(key, values) { try { localStorage.setItem(key,JSON.stringify([...new Set(values)])); }catch{} }
function toggleStored(key,id) { const ids=storageRead(key), idx=ids.indexOf(Number(id)); if(idx>=0)ids.splice(idx,1);else ids.push(Number(id)); storageWrite(key,ids); }
const state = { leagues:[], groups:[], selectedLeague:null, date:'', filter:'todos', mode:'liga', q:'', selectedGame:null, collapsed:new Set() };
const dtFmt = iso => { if(!iso)return '—'; const date=iso.slice(0,10).split('-'); return date.length===3?`${date[2]}/${date[1]}`:safe(iso); };
const weekday = iso => { try {const d=new Date(iso.slice(0,10)+'T12:00:00');return d.toLocaleDateString('pt-BR',{weekday:'short'}).replace('.','').toUpperCase();}catch{return 'DATA';} };
const niceDate = iso => { if(!iso)return '—';return `${weekday(iso)} ${dtFmt(iso)}`; };
const matches = () => state.groups.flatMap(group=>group.jogos.map(game=>({...game, dfGroup:group})));
function safeLogo(src,alt,cls='') {
  const url=String(src||'').trim();
  if (!/^https?:\/\//i.test(url) && !url.startsWith('/static/')) {
    const initials=String(alt||'DF').trim().split(/\s+/).slice(0,2).map(x=>x[0]||'').join('').toUpperCase();
    return `<span class="df-img-fallback ${cls}" role="img" aria-label="${safe(alt||'Escudo indisponível')}">${safe(initials||'DF')}</span>`;
  }
  return `<img class="${cls}" src="${safe(url)}" alt="${safe(alt||'Escudo')}" loading="lazy" decoding="async">`;
}
function leagueHref(id) { return `/liga/${encodeURIComponent(id)}`; }
function renderKpis() {
  const all=matches();const leagues=new Set(all.map(x=>x.campeonato_id));
  const clubs=new Set(all.flatMap(x=>[x.casa_id,x.fora_id]).filter(Boolean));
  const goals=all.reduce((v,g)=>v+Number(g.gols_casa||0)+Number(g.gols_fora||0),0);
  const values=[['Partidas registradas',all.length,'Últimas rodadas disponíveis','calendar'], ['Ligas representadas',leagues.size,'Competições nos resultados','shield'], ['Clubes em campo',clubs.size,'Equipes distintas','users'], ['Gols registrados',goals,'Nas partidas exibidas','chart']];
  $('#df-kpis').innerHTML=values.map(([label,value,sub,glyph])=>`<article class="df-kpi"><div class="df-kpi-label">${icon(glyph,18)}<span>${label}</span></div><div class="df-kpi-value" data-count="${value}">0</div><div class="df-kpi-foot">${sub}</div></article>`).join('');
  const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
  if(reduce){$$('[data-count]').forEach(el=>el.textContent=Number(el.dataset.count).toLocaleString('pt-BR'));return;}
  const start=performance.now(); const items=$$('[data-count]');
  function frame(now) {const ratio=Math.min(1,(now-start)/600);const eased=1-(1-ratio)**3;items.forEach(el=>el.textContent=Math.floor(Number(el.dataset.count)*eased).toLocaleString('pt-BR'));if(ratio<1)requestAnimationFrame(frame);}
  requestAnimationFrame(frame);
  $('#df-data-scope').textContent='Dados históricos · Últimas rodadas';
}
function renderLeagues() {
  const box=$('#lista-ligas');
  const favs=new Set(storageRead(LEAGUE_KEY));
  const filtered=state.leagues.filter(l=>l.nome).sort((a,b)=>{
    const fa=favs.has(Number(a.id)),fb=favs.has(Number(b.id));
    if(fa!==fb)return fa?-1:1;
    return (b.total_jogos||0)-(a.total_jogos||0) || (a.nome||'').localeCompare(b.nome||'','pt');
  });
  $('#df-league-count').textContent=String(filtered.length);
  if(!filtered.length){box.innerHTML='<div class="df-empty-inline">Nenhuma liga com partidas registradas.</div>';return;}
  box.innerHTML=`<button type="button" class="df-league-item df-all-leagues ${state.selectedLeague===null?'active':''}" data-league-filter=""><span class="df-league-icon">${icon('chart',18)}</span><span class="df-league-text">Todas as ligas</span></button>`+filtered.map(l=>{
    const favored=favs.has(Number(l.id));
    return `<div class="df-league-item ${state.selectedLeague===Number(l.id)?'active':''}"><button type="button" class="df-league-select" data-league="${l.id}" title="Ver ${safe(l.nome)}">${safeLogo(l.logo,l.nome)}<span class="df-league-text">${safe(l.nome)}</span></button><button class="df-star ${favored?'active':''}" type="button" aria-label="${favored?'Remover liga dos favoritos':'Adicionar liga aos favoritos'}" aria-pressed="${favored}" data-star-league="${l.id}">${icon('star',17)}</button></div>`;
  }).join('');
  $$('[data-star-league]',box).forEach(btn=>btn.addEventListener('click',()=>{toggleStored(LEAGUE_KEY,btn.dataset.starLeague);renderLeagues();renderFeed();}));
  $$('[data-league]',box).forEach(btn=>btn.addEventListener('click',()=>{location.href=leagueHref(btn.dataset.league);}));
  $('[data-league-filter=""]',box)?.addEventListener('click',()=>{state.selectedLeague=null;renderLeagues();renderFeed();});
}
function renderDates() {
  const dates=[...new Set(matches().map(x=>x.data?.slice(0,10)).filter(Boolean))].sort((a,b)=>b.localeCompare(a));
  $('#df-date-tabs').innerHTML = `<button class="df-date-btn ${!state.date?'active':''}" type="button" data-date="" aria-pressed="${!state.date}"><span>PERÍODO</span><strong>Todas</strong></button>` +
    dates.map(d=>`<button class="df-date-btn ${state.date===d?'active':''}" type="button" data-date="${safe(d)}" aria-pressed="${state.date===d}"><span>${weekday(d)}</span><strong>${dtFmt(d)}</strong></button>`).join('');
  $$('[data-date]','#df-date-tabs'.startsWith('#')?$('#df-date-tabs'):document).forEach(btn=>btn.addEventListener('click',()=>{state.date=btn.dataset.date;renderDates();renderFeed();}));
}
function visibleGames() {
  const favorited=new Set(storageRead(MATCH_KEY)), needle=state.q.toLocaleLowerCase('pt-BR');
  return matches().filter(game=>{
    if(state.selectedLeague && Number(game.campeonato_id)!==state.selectedLeague) return false;
    if(state.date && game.data?.slice(0,10)!==state.date) return false;
    if(state.filter==='favoritos' && !favorited.has(Number(game.id)))return false;
    // O endpoint só retorna jogos concluídos.
    if(needle && !`${game.casa||''} ${game.fora||''} ${game.campeonato||''} ${game.dfGroup?.pais||''}`.toLocaleLowerCase('pt-BR').includes(needle))return false;
    return true;
  });
}
function matchRow(j) {
  const fav=storageRead(MATCH_KEY).includes(Number(j.id));
  const selected=Number(j.id)===Number(state.selectedGame);
  const casaScore=j.gols_casa??'—',foraScore=j.gols_fora??'—';
  return `<div class="df-game-row ${selected?'selected':''}" data-match="${j.id}" tabindex="0" role="button" aria-label="Ver detalhes: ${safe(j.casa)} ${safe(casaScore)} a ${safe(foraScore)} ${safe(j.fora)}" aria-pressed="${selected}">
  <div class="df-game-date"><span class="df-ft">FT</span><span>${dtFmt(j.data)}</span></div>
  <div class="df-game-teams"><div class="df-game-team">${safeLogo(j.casa_logo,j.casa)}<span>${j.casa_id?`<a href="/clube/${j.casa_id}" class="entity-link">${safe(j.casa)}</a>`:safe(j.casa)}</span></div><div class="df-game-team">${safeLogo(j.fora_logo,j.fora)}<span>${j.fora_id?`<a href="/clube/${j.fora_id}" class="entity-link">${safe(j.fora)}</a>`:safe(j.fora)}</span></div></div>
  <div class="df-game-scores"><span>${safe(casaScore)}</span><span>${safe(foraScore)}</span></div>
  <div class="df-game-actions"><button type="button" class="df-star ${fav?'active':''}" data-favorite-game="${j.id}" aria-label="${fav?'Desfavoritar partida':'Favoritar partida'}" aria-pressed="${fav}">${icon('star',17)}</button>${icon('arrow',17)}</div></div>`;
}
function renderFeed() {
  const visible=visibleGames();$('#df-games-count').textContent=`${visible.length} partida${visible.length===1?'':'s'}`;
  if(!visible.length){$('#feed').innerHTML=`<div class="df-empty"><div class="df-empty-icon">${icon('search',28)}</div><h3>Nenhuma partida encontrada</h3><p>Tente outra data, busca ou filtro.</p><button class="df-primary-btn" type="button" id="df-clear-filter">Limpar filtros</button></div>`;$('#df-clear-filter').addEventListener('click',()=>{state.q='';state.date='';state.filter='todos';$('#busca').value='';renderDates();updateFilterButtons();renderFeed();});return;}
  const sections=[];
  if(state.mode==='liga') {
    const byLeague=new Map();
    for(const game of visible){const key=String(game.campeonato_id);if(!byLeague.has(key))byLeague.set(key,{group:game.dfGroup,jogos:[]});byLeague.get(key).jogos.push(game);}
    byLeague.forEach(({group,jogos},id)=>sections.push(`<section class="df-game-group"><div class="df-game-group-head"><button class="df-group-collapse" data-collapse="liga-${id}" type="button" aria-expanded="${!state.collapsed.has('liga-'+id)}">${safeLogo(group.logo,group.campeonato)}<span class="df-group-titles"><strong>${safe(group.campeonato||'Liga')}</strong><small>${safe(group.pais||'Competição')}</small></span><span class="df-group-count">${jogos.length}</span><span class="df-chevron">${icon('chevron',17)}</span></button><a class="df-group-open" href="${leagueHref(id)}" aria-label="Abrir liga ${safe(group.campeonato)}" title="Abrir liga">${icon('arrow',16)}</a></div><div class="df-group-matches" ${state.collapsed.has('liga-'+id)?'hidden':''}>${jogos.map(matchRow).join('')}</div></section>`));
  } else {
    const byDate=new Map();
    visible.sort((a,b)=>String(b.data).localeCompare(String(a.data)));
    for(const game of visible){const key=game.data?.slice(0,10)||'sem-data';if(!byDate.has(key))byDate.set(key,[]);byDate.get(key).push(game);}
    byDate.forEach((jogos,id)=>sections.push(`<section class="df-game-group"><div class="df-game-group-head"><button type="button" class="df-group-collapse" data-collapse="data-${id}" aria-expanded="${!state.collapsed.has('data-'+id)}"><span class="df-league-icon">${icon('calendar',19)}</span><span class="df-group-titles"><strong>${niceDate(id)}</strong><small>Resultados por data</small></span><span class="df-group-count">${jogos.length}</span><span class="df-chevron">${icon('chevron',17)}</span></button></div><div class="df-group-matches" ${state.collapsed.has('data-'+id)?'hidden':''}>${jogos.map(matchRow).join('')}</div></section>`));
  }
  $('#feed').innerHTML=sections.join('');
  $$('[data-collapse]','#feed'.startsWith('#')?$('#feed'):document).forEach(btn=>btn.addEventListener('click',()=>{const key=btn.dataset.collapse;state.collapsed.has(key)?state.collapsed.delete(key):state.collapsed.add(key);renderFeed();}));
  $$('[data-favorite-game]',$('#feed')).forEach(btn=>btn.addEventListener('click',event=>{event.stopPropagation();toggleStored(MATCH_KEY,btn.dataset.favoriteGame);renderFeed();}));
  $$('[data-match]',$('#feed')).forEach(row=>{
    const open=()=>selectMatch(Number(row.dataset.match));
    row.addEventListener('click',e=>{if(e.target.closest('a,button'))return;open();});
    row.addEventListener('keydown',e=>{if(e.target!==row)return;if(e.key==='Enter'||e.key===' '){e.preventDefault();open();}});
  });
}
function updateFilterButtons() {
  $$('[data-filter]',$('#df-filters')).forEach(btn=>{const active=btn.dataset.filter===state.filter;btn.classList.toggle('active',active);btn.setAttribute('aria-pressed',String(active));});
}
function detailScore(j) {return `${j.gols_casa??'—'} <span>:</span> ${j.gols_fora??'—'}`;}
async function selectMatch(id) {
  state.selectedGame=id;renderFeed();
  const panel=$('#df-detail-panel');
  panel.innerHTML='<div class="df-detail-loading"><div class="df-skeleton-bar"></div><div class="df-skeleton-bar"></div><div class="df-skeleton-bar"></div></div>';
  const match=matches().find(j=>Number(j.id)===id);
  if(!match)return;
  try{
    const res=await fetch(`/api/jogo/${encodeURIComponent(id)}`);
    if(!res.ok)throw Error(`Erro HTTP ${res.status}`);
    const data=await res.json();
    if(state.selectedGame!==id)return;
    const matchDate=(data.data||match.data||'').slice(0,10);
    const casa=data.estatisticas?.completo?.Casa||{};
    const fora=data.estatisticas?.completo?.Fora||{};
    // Não inventar campos: listar somente valores reais existentes.
    const metrics=[['posse_bola','Posse de bola','%'],['chutes_total','Chutes',''],['chutes_certos','Chutes no gol',''],['passes_certos','Passes certos',''],['escanteios','Escanteios',''],['faltas_cometidas','Faltas cometidas','']];
    const stats=metrics.filter(([key])=>casa[key]!=null||fora[key]!=null).slice(0,5);
    const market=data.odds||{};
    const oddItems=[['1',market.odd_casa],['X',market.odd_empate],['2',market.odd_fora]].filter(([,v])=>v!=null&&Number.isFinite(Number(v))&&Number(v)>0);
    const oddHtml=oddItems.length?`<div class="df-detail-odds"><h3>Odds registradas</h3><div class="df-odds-list">${oddItems.map(([label,value])=>`<button type="button" class="df-odd-chip" aria-pressed="false"><small>${label}</small><strong>${Number(value).toFixed(2)}</strong></button>`).join('')}</div><p>Valores históricos armazenados, não cotações ao vivo.</p></div>`:'';
    const renderStat=([key,label,suffix])=>`<div class="df-detail-stat"><span>${safe(casa[key]??'—')}${casa[key]==null?'':suffix}</span><span>${label}</span><span>${safe(fora[key]??'—')}${fora[key]==null?'':suffix}</span></div>`;
    panel.innerHTML=`<div class="df-detail-head"><div><span class="df-overline">DETALHES DA PARTIDA</span><h2>${safe(data.campeonato||match.campeonato)}</h2><p>${safe(data.rodada||'Resultado registrado')} · ${dtFmt(matchDate)}</p></div><button type="button" class="df-icon-button" id="df-close-detail" title="Fechar detalhes" aria-label="Fechar detalhes">${icon('x',18)}</button></div>
      <div class="df-detail-score"><div class="df-detail-team">${safeLogo(data.casa_logo||match.casa_logo,data.casa||match.casa)}<strong>${safe(data.casa||match.casa)}</strong></div><div class="df-score-number">${detailScore(data)}</div><div class="df-detail-team">${safeLogo(data.fora_logo||match.fora_logo,data.fora||match.fora)}<strong>${safe(data.fora||match.fora)}</strong></div></div><div class="df-detail-ft"><span class="df-ft">FT</span> Partida encerrada</div>
      <div class="df-detail-divider"></div>
      <div class="df-detail-section"><h3>Resumo da partida</h3>${stats.length?stats.map(renderStat).join(''):'<p class="df-muted">Estatísticas detalhadas não disponíveis para esta partida.</p>'}</div>
      ${oddHtml}
      ${data.estadio?`<div class="df-detail-venue">Estádio <strong>${safe(data.estadio)}</strong></div>`:''}
      <a class="df-detail-link" href="/jogo/${id}">Análise completa da partida ${icon('arrow',18)}</a>`;
    $('#df-close-detail').addEventListener('click',()=>{state.selectedGame=null;renderFeed();renderEmptyDetail();});
    panel.querySelectorAll('.df-odd-chip').forEach(btn=>btn.addEventListener('click',()=>{
      const selected=btn.getAttribute('aria-pressed')==='true';
      panel.querySelectorAll('.df-odd-chip').forEach(b=>b.setAttribute('aria-pressed','false'));
      btn.setAttribute('aria-pressed',String(!selected));
    }));
    if(window.innerWidth<=1250)panel.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
  }catch(error){if(state.selectedGame!==id)return;panel.innerHTML=`<div class="df-empty"><h3>Não foi possível carregar</h3><p>${safe(error.message)}</p><a class="df-detail-link" href="/jogo/${id}">Abrir página da partida</a></div>`;}
}
function renderEmptyDetail(){ $('#df-detail-panel').innerHTML=`<div class="df-detail-empty"><div class="df-detail-graphic" aria-hidden="true">${icon('shield',32)}</div><h2>Escolha uma partida</h2><p>Selecione um resultado ao lado para consultar as informações detalhadas.</p></div>`; }
async function load() {
  const results=await Promise.all([fetch('/api/ligas'),fetch('/api/jogos?limite=200')]);
  for(const res of results)if(!res.ok)throw new Error(`Falha ao consultar o servidor (${res.status})`);
  const [leagues,games]=await Promise.all(results.map(r=>r.json()));
  state.leagues=Array.isArray(leagues.ligas)?leagues.ligas:[];
  state.groups=Array.isArray(games.grupos)?games.grupos:[];
  // O /api/jogos não oferece filtro por datas arbitrárias: abas mostram somente datas que existem na resposta.
  state.groups.forEach(g=>{if(!Array.isArray(g.jogos))g.jogos=[];});
  state.groups.forEach(group=>group.jogos.forEach(g=>{g.campeonato_id=group.campeonato_id;g.campeonato=group.campeonato;}));
  renderKpis();renderLeagues();renderDates();renderFeed();renderEmptyDetail();
}
function setup() {
  const input=$('#busca');
  const starting=new URLSearchParams(location.search).get('busca');
  if(starting){state.q=starting.trim();input.value=state.q;}
  input?.addEventListener('input',ev=>{state.q=ev.target.value.trim();renderFeed();});
  $('#df-filters').addEventListener('click',ev=>{const btn=ev.target.closest('[data-filter]');if(!btn)return;state.filter=btn.dataset.filter;updateFilterButtons();renderFeed();});
  $$('.df-switch button').forEach(btn=>btn.addEventListener('click',()=>{state.mode=btn.dataset.mode;$$('.df-switch button').forEach(b=>{const active=b===btn;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});renderFeed();}));
  load().catch(error=>{const message=safe(error.message);$('#feed').innerHTML=`<div class="df-error"><h3>Não foi possível carregar os jogos</h3><p>${message}</p><button id="df-retry" type="button" class="df-primary-btn">Tentar novamente</button></div>`;$('#df-kpis').innerHTML='';$('#df-date-tabs').innerHTML='';$('#df-league-count').textContent='—';$('#df-retry').addEventListener('click',()=>location.reload());});
}
setup();
