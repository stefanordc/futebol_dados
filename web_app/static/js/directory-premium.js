/* Diretórios de jogadores, técnicos, árbitros e apostas — dados existentes na API. */
const root=document.getElementById('conteudo');
const path=location.pathname.split('/').filter(Boolean).pop()||'';
const PAGES={jogadores:['Jogadores','/api/stats/individuais'],tecnicos:['Técnicos','/api/stats/tecnicos'],arbitros:['Árbitros','/api/stats/arbitros']};
const safe=window.DF?.escape||(value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])));
const icon=window.DF?.icon||(()=> '');
const text=v=>String(v??'').toLocaleLowerCase('pt-BR');
const pageSize=36;
let all=[],query='',offset=0,seq=0;
const selected={campeonato_id:'',clube_id:'',posicao:'',nacionalidade:''};
let meta={ligas:[],clubes:[],posicoes:[],nacionalidades:[]};
function image(src,name){const url=String(src||'');return /^https?:\/\//.test(url)?`<img src="${safe(url)}" loading="lazy" alt="${safe(name)}">`:`<span class="df-dir-fallback" aria-label="Imagem não disponível">${safe(String(name||'?').slice(0,2).toUpperCase())}</span>`;}
function identity(row){
 const name=row.nome||'Sem nome';
 if(path==='jogadores')return {name,subtitle:[row.clube,row.posicao].filter(Boolean).join(' · '),photo:row.foto,href:row.jogador_id?`/jogador/${row.jogador_id}`:null,badge:row.rating_medio!=null?`Nota ${Number(row.rating_medio).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2})}`:'Sem nota',meta:[row.nacionalidade,row.jogos!=null?`${row.jogos} jogos`:null].filter(Boolean).join(' · ')};
 if(path==='tecnicos')return {name,subtitle:row.clube||'Técnico',photo:row.foto,href:row.id?`/tecnico/${row.id}`:null,badge:row.jogos!=null?`${row.jogos} jogos`:'—',meta:[row.nacionalidade,row.pts!=null?`${row.pts} pontos`:null].filter(Boolean).join(' · ')};
 return {name,subtitle:row.pais||'Árbitro',photo:row.foto,href:row.id?`/arbitro/${row.id}`:null,badge:row.jogos!=null?`${row.jogos} jogos`:'—',meta:row.amarelos_por_jogo!=null?`${row.amarelos_por_jogo} amarelos/jogo`:''};
}
function optionList(items,idKey,labelKey,first){return `<option value="">${first}</option>`+items.map(it=>typeof it==='string'?`<option value="${safe(it)}">${safe(it)}</option>`:`<option value="${safe(it[idKey])}">${safe(it[labelKey])}</option>`).join('');}
function renderFilters(){
 const pane=document.getElementById('df-dir-filters');if(!pane)return;
 if(path==='arbitros'){pane.innerHTML='';return;}
 pane.innerHTML=`<label>Liga<select data-dir-filter="campeonato_id">${optionList(meta.ligas,'id','nome','Todas as ligas')}</select></label><label>Clube<select data-dir-filter="clube_id">${optionList(meta.clubes,'id','clube','Todos os clubes')}</select></label><label>Posição<select data-dir-filter="posicao" ${path==='tecnicos'?'disabled title="Posição em campo não se aplica a técnicos"':''}>${optionList(meta.posicoes,'','',path==='tecnicos'?'Não se aplica':'Todas as posições')}</select></label><label>Nacionalidade<select data-dir-filter="nacionalidade">${optionList(meta.nacionalidades,'','', 'Todas as nacionalidades')}</select></label>`;
 pane.querySelectorAll('select[data-dir-filter]').forEach(sel=>{sel.value=selected[sel.dataset.dirFilter]||'';sel.addEventListener('change',()=>{selected[sel.dataset.dirFilter]=sel.value;offset=0;loadResults();});});
}
function renderCards(){
 const filtered=all.filter(row=>{
  const nameOK=text([row.nome,row.clube,row.nacionalidade,row.pais,row.posicao].join(' ')).includes(text(query));
  const clubOK=path!=='tecnicos'||!selected.clube_id||text(row.clube)===text(meta.clubes.find(c=>String(c.id)===selected.clube_id)?.clube||'');
  const nacOK=path!=='tecnicos'||!selected.nacionalidade||text(row.nacionalidade)===text(selected.nacionalidade);
  return nameOK&&clubOK&&nacOK;
 });
 const results=filtered.slice(0,offset+pageSize),count=document.getElementById('df-dir-count'),box=document.getElementById('df-dir-list');
 if(!count||!box)return;
 count.textContent=`${filtered.length} resultado${filtered.length===1?'':'s'}${path==='jogadores'?' · até 200 por consulta':''}`;
 box.innerHTML=results.length?results.map(r=>{const item=identity(r),tag=item.href?'a':'div',href=item.href?` href="${item.href}"`:'';return `<${tag} class="df-person-card"${href}>${image(item.photo,item.name)}<div class="df-person-body"><h3>${safe(item.name)}</h3><p>${safe(item.subtitle)}</p><span class="df-person-meta">${safe(item.meta)}</span></div><span class="df-person-badge">${safe(item.badge)}</span>${item.href?`<span class="df-person-arrow">${icon('arrow',18)}</span>`:''}</${tag}>`;}).join(''):`<div class="df-empty"><h3>Nenhum registro encontrado</h3><p>Altere os filtros ou a busca.</p></div>`;
 document.getElementById('df-dir-more').hidden=results.length>=filtered.length;
}
function layout(title,description){
 root.innerHTML=`<div class="df-directory-hero"><div class="df-eyebrow">BASE DE DADOS</div><h1>${safe(title)}</h1><p>${safe(description)}</p></div><div class="df-dir-tools"><label class="df-directory-search">${icon('search',18)}<input type="search" id="df-dir-search" placeholder="Buscar por nome, clube ou país" aria-label="Buscar registros"></label><span id="df-dir-count" class="df-count">Carregando…</span></div><div id="df-dir-filters" class="df-dir-filters"></div><div id="df-dir-list" class="df-person-grid" aria-live="polite"><div class="df-loading-card df-skeleton"></div></div><div class="df-dir-pagination"><button type="button" id="df-dir-more" class="df-secondary-btn" hidden>Mostrar mais registros</button></div>`;
 document.getElementById('df-dir-search').addEventListener('input',e=>{query=e.target.value;offset=0;renderCards();});
 document.getElementById('df-dir-more').addEventListener('click',()=>{offset+=pageSize;renderCards();});
}
async function loadResults(){
 const token=++seq,box=document.getElementById('df-dir-list');if(!box)return;
 box.innerHTML='<div class="df-loading-card df-skeleton"></div>';
 const q=new URLSearchParams();
 if(selected.campeonato_id)q.set('campeonato_id',selected.campeonato_id);
 let url=PAGES[path][1];
 if(path==='jogadores'){
  q.set('metrica','rating');q.set('limite','200');q.set('ordenar','rating_medio');
  for(const key of ['clube_id','posicao','nacionalidade'])if(selected[key])q.set(key,selected[key]);
 }else if(path==='tecnicos')q.set('ordenar','jogos');
 try{const response=await fetch(url+'?'+q.toString());if(!response.ok)throw Error('HTTP '+response.status);const d=await response.json();if(token!==seq)return;all=d.itens||[];if(path==='jogadores'&&d.filtros&&meta.clubes.length===0){meta.clubes=d.filtros.clubes||[];meta.posicoes=d.filtros.posicoes||[];meta.nacionalidades=d.filtros.nacionalidades||[];renderFilters();}renderCards();}
 catch(e){if(token===seq){box.innerHTML=`<div class="df-error">Erro ao consultar o diretório: ${safe(e.message)}</div>`;document.getElementById('df-dir-count').textContent='Indisponível';}}
}
async function loadDirectory(){
 const [title]=PAGES[path];document.title=`${title} | Dados Futebol`;layout(title,path==='jogadores'?'Ordenação por nota média dos jogadores.':'Perfis e indicadores disponíveis no banco de dados.');
 try{
  const [leagueData,filterData]=await Promise.all([
   fetch('/api/ligas').then(r=>r.ok?r.json():{ligas:[]}).catch(()=>({ligas:[]})),
   fetch('/api/stats/individuais?metrica=rating&limite=5').then(r=>r.ok?r.json():{filtros:{}}).catch(()=>({filtros:{}})),
  ]);
  meta.ligas=leagueData.ligas||[];
  meta.clubes=filterData.filtros?.clubes||[];
  meta.posicoes=filterData.filtros?.posicoes||[];
  meta.nacionalidades=filterData.filtros?.nacionalidades||[];
 }catch(e){console.warn('Metadados de filtros indisponíveis',e);}
 renderFilters();await loadResults();
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
