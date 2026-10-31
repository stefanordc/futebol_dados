/* Diretórios de jogadores, técnicos, árbitros e apostas — dados existentes na API. */
const root=document.getElementById('conteudo');
const path=location.pathname.split('/').filter(Boolean).pop()||'';
const PAGES={jogadores:['Jogadores','/api/stats/individuais?metrica=gols&limite=200'],tecnicos:['Técnicos','/api/stats/tecnicos'],arbitros:['Árbitros','/api/stats/arbitros']};
const safe=window.DF?.escape||(value=>String(value??''));
const icon=window.DF?.icon||(()=> '');
let all=[];
let query='';
let offset=0;
const pageSize=36;
const text=v=>String(v??'').toLocaleLowerCase('pt-BR');
function image(src,name){const url=String(src||'');return /^https?:\/\//.test(url)?`<img src="${safe(url)}" loading="lazy" alt="${safe(name)}">`:`<span class="df-dir-fallback" aria-label="Imagem não disponível">${safe(String(name||'?').split(/\s+/).slice(0,2).map(s=>s[0]||'').join('').toUpperCase())}</span>`;}
function identity(row) {
  const name=row.nome||'Sem nome';
  if(path==='jogadores')return {name,subtitle:[row.clube,row.posicao].filter(Boolean).join(' · '),photo:row.foto,href:row.jogador_id?`/jogador/${row.jogador_id}`:null,badge:row.jogos!=null?`${row.jogos} jogos`:'—',meta:row.nacionalidade||''};
  if(path==='tecnicos')return {name,subtitle:row.clube||'Técnico',photo:row.foto,href:row.id?`/tecnico/${row.id}`:null,badge:row.jogos!=null?`${row.jogos} jogos`:'—',meta:row.pts!=null?`${row.pts} pontos`:''};
  return {name,subtitle:row.pais||'Árbitro',photo:row.foto,href:row.id?`/arbitro/${row.id}`:null,badge:row.jogos!=null?`${row.jogos} jogos`:'—',meta:row.amarelos_por_jogo!=null?`${row.amarelos_por_jogo} amarelos/jogo`:''};
}
function renderCards(){
  const filtered=all.filter(row=>text([row.nome,row.clube,row.nacionalidade,row.pais,row.posicao].join(' ')).includes(text(query)));
  const results=filtered.slice(0,offset+pageSize);
  document.getElementById('df-dir-count').textContent=`${filtered.length} resultado${filtered.length===1?'':'s'}`;
  const box=document.getElementById('df-dir-list');
  box.innerHTML=results.length?results.map(r=>{
    const item=identity(r);const tag=item.href?'a':'div';const href=item.href?` href="${item.href}"`:'';
    return `<${tag} class="df-person-card"${href}>${image(item.photo,item.name)}<div class="df-person-body"><h3>${safe(item.name)}</h3><p>${safe(item.subtitle)}</p><span class="df-person-meta">${safe(item.meta)}</span></div><span class="df-person-badge">${safe(item.badge)}</span>${item.href?`<span class="df-person-arrow">${icon('arrow',18)}</span>`:''}</${tag}>`;
  }).join(''):`<div class="df-empty"><div class="df-empty-icon">${icon('search',28)}</div><h3>Nenhum registro encontrado</h3><p>Altere a busca ou utilize as estatísticas para explorar outros registros.</p></div>`;
  const more=document.getElementById('df-dir-more');more.hidden=results.length>=filtered.length;
}
function layout(title,description){
  root.innerHTML=`<div class="df-directory-hero"><div class="df-eyebrow">BASE DE DADOS</div><h1>${safe(title)}</h1><p>${safe(description)}</p></div><div class="df-dir-tools"><label class="df-directory-search">${icon('search',18)}<input type="search" id="df-dir-search" placeholder="Buscar por nome, clube ou país" aria-label="Buscar registros"></label><span id="df-dir-count" class="df-count">Carregando…</span></div><div id="df-dir-list" class="df-person-grid" aria-live="polite"><div class="df-loading-card df-skeleton"></div><div class="df-loading-card df-skeleton"></div><div class="df-loading-card df-skeleton"></div></div><div class="df-dir-pagination"><button type="button" id="df-dir-more" class="df-secondary-btn" hidden>Mostrar mais registros</button></div>`;
  document.getElementById('df-dir-search').addEventListener('input',e=>{query=e.target.value;offset=0;renderCards();});
  document.getElementById('df-dir-more').addEventListener('click',()=>{offset+=pageSize;renderCards();});
}
async function loadDirectory(){
  const [title,url]=PAGES[path];
  document.title=`${title} | Dados Futebol`;
  layout(title,'Perfis e indicadores disponíveis no banco de dados.');
  try{
    const res=await fetch(url);if(!res.ok)throw new Error('Falha HTTP '+res.status);
    const data=await res.json();all=Array.isArray(data.itens)?data.itens:[];renderCards();
  }catch(err){document.getElementById('df-dir-list').innerHTML=`<div class="df-error"><h3>Não foi possível carregar o diretório</h3><p>${safe(err.message)}</p></div>`;document.getElementById('df-dir-count').textContent='Indisponível';}
}
async function loadBetting(){
  document.title='Apostas | Dados Futebol';
  root.innerHTML=`<div class="df-directory-hero"><div class="df-eyebrow">ANÁLISE RESPONSÁVEL</div><h1>Mercados e probabilidades</h1><p>Consulte estatísticas, resultados e odds históricas disponíveis nas páginas das partidas. Não são cotações em tempo real.</p></div><div class="df-bet-actions"><a class="df-primary-btn" href="/estatisticas">Explorar estatísticas ${icon('arrow',18)}</a><a href="/" class="df-secondary-btn">Ver resultados</a></div><section class="section df-bets-section"><div class="df-panel-heading"><div><div class="df-overline">BASE HISTÓRICA</div><h2>Partidas registradas</h2></div><span class="df-count">Últimas rodadas</span></div><div id="df-bets-games" class="df-bets-games"><div class="loading">Carregando partidas…</div></div></section>`;
  try {
    const res=await fetch('/api/jogos?limite=40');if(!res.ok)throw new Error('Falha HTTP '+res.status);
    const data=await res.json();const games=(data.grupos||[]).flatMap(g=>(g.jogos||[]).map(j=>({...j,campeonato:g.campeonato})));
    document.getElementById('df-bets-games').innerHTML=games.length?games.slice(0,16).map(j=>`<div class="df-bet-entry"><div class="df-bet-game"><a class="df-bet-teams" href="/jogo/${j.id}">${safe(j.casa)} <strong>${safe(j.gols_casa??'—')} : ${safe(j.gols_fora??'—')}</strong> ${safe(j.fora)}</a><button type="button" class="df-secondary-btn df-bet-odds-button" data-bet-detail="${j.id}">Ver odds ${icon('chevron',16)}</button></div><div class="df-bet-odds" data-bet-odds="${j.id}" hidden></div></div>`).join(''):'<div class="df-empty">Nenhuma partida disponível no momento.</div>';
    document.querySelectorAll('[data-bet-detail]').forEach(btn=>btn.addEventListener('click',async()=>{
      const box=document.querySelector(`[data-bet-odds="${btn.dataset.betDetail}"]`);
      if(!box.hidden){box.hidden=true;btn.setAttribute('aria-expanded','false');return;}
      btn.setAttribute('aria-expanded','true');box.hidden=false;
      if(box.dataset.loaded)return;
      box.textContent='Consultando odds registradas…';
      try{
        const response=await fetch(`/api/jogo/${btn.dataset.betDetail}`);
        if(!response.ok)throw new Error('Falha HTTP '+response.status);
        const detail=await response.json();const odds=detail.odds||{};
        const items=[['1',odds.odd_casa],['X',odds.odd_empate],['2',odds.odd_fora]].filter(([,v])=>v!=null&&Number.isFinite(Number(v))&&Number(v)>0);
        box.innerHTML=items.length?`<div class="df-odds-list">${items.map(([label,val])=>`<button class="df-odd-chip" type="button" aria-pressed="false"><small>${label}</small><strong>${Number(val).toFixed(2)}</strong></button>`).join('')}</div><p class="df-muted">Odds históricas registradas, não cotações em tempo real.</p>`:'<p class="df-muted">Sem odds registradas para esta partida.</p>';
        box.dataset.loaded='true';
        box.querySelectorAll('.df-odd-chip').forEach(oddBtn=>oddBtn.addEventListener('click',()=>{const pressed=oddBtn.getAttribute('aria-pressed')==='true';box.querySelectorAll('.df-odd-chip').forEach(b=>b.setAttribute('aria-pressed','false'));oddBtn.setAttribute('aria-pressed',String(!pressed));}));
      }catch(err){box.textContent='Não foi possível carregar as odds: '+err.message;}
    }));
  }catch(err){document.getElementById('df-bets-games').innerHTML=`<div class="df-error">${safe(err.message)}</div>`;}
}
if(PAGES[path])loadDirectory();else if(path==='apostas')loadBetting();
