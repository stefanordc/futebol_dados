/** Dados Futebol — finalizações realizadas, sofridas e gols.
 * Complemento de interface: usa apenas APIs FastAPI existentes.
 */
(() => {
  'use strict';
  if (window.__dfStatsExtra) return;
  window.__dfStatsExtra = true;

  const $ = (sel, root = document) => root.querySelector(sel);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const compact = (n) => Number(n || 0).toLocaleString('pt-BR');
  const pct = (num, den) => den ? (100 * num / den).toLocaleString('pt-BR', {maximumFractionDigits:1}) + '%' : '—';
  const normalize = (value) => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]/g,'');
  const positive = (value) => Number.isFinite(Number(value)) && Number(value) > 0;
  const isGoal = (s) => /gol|goal/.test(normalize(s?.tipo_evento));
  const isSave = (s) => Boolean(s?.foi_no_alvo) || /defendid|saved|save/.test(normalize(s?.tipo_evento));
  const goalAgainst = (s) => s?.foi_gol_contra === true || s?.foi_gol_contra === 1 || s?.foi_gol_contra === 'true';
  const goalForTeam = (shot, id) => isGoal(shot) && (goalAgainst(shot) ? Number(shot.clube_id) !== id : Number(shot.clube_id) === id);
  const mapCache = new Map();
  const teamCache = new Map();
  const detailCache = new Map();
  let mode = 'realizadas';
  const sofridasState={page:1,ordenar:'gols',ordem:'desc',selected:null};
  let seq = 0;
  let originalMapId = null;
  let originalMapShots = [];
  let originalMapFilter = 'todos';
  let suppressMutation = false;

  function scope() {
    return {
      pais: $('#sel-pais')?.value || '',
      campeonato_id: $('#sel-liga')?.value || '',
      temporada: $('#sel-temp')?.value || '',
      mando: $('#sel-mando')?.value || 'todos',
    };
  }
  function withScope(extra = {}) {
    const q = new URLSearchParams();
    Object.entries({...scope(), ...extra}).forEach(([k, v]) => {
      if (v != null && v !== '' && v !== 'todos') q.set(k, String(v));
    });
    return q;
  }
  async function json(url) {
    const r = await fetch(url, {headers: {'Accept':'application/json'}});
    if (!r.ok) throw new Error(`Erro HTTP ${r.status} em ${new URL(url, location.href).pathname}`);
    return r.json();
  }
  function labelOfClub(id) {
    const opt = [...($('#sel-clube')?.options || [])].find(x => Number(x.value) === Number(id));
    return opt?.textContent?.trim() || `Clube #${id}`;
  }
  function getTeamId() { return Number($('#sel-clube')?.value)||null; }

  function shotPosition(s) {
    if (Number.isFinite(Number(s.left)) && Number.isFinite(Number(s.top)) && s.left != null && s.top != null) {
      return {left: Math.max(0, Math.min(100, Number(s.left))), top: Math.max(0, Math.min(100, Number(s.top)))};
    }
    if (s.coordenada_x == null || s.coordenada_y == null) return null;
    const x = Number(s.coordenada_x), y = Number(s.coordenada_y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return {left:Math.max(0,Math.min(100,100*y/68)),top:Math.max(0,Math.min(100,100*(105-x)/105))};
  }
  function shotKind(s) { return isGoal(s) ? 'gol' : isSave(s) ? 'certa' : 'outra'; }
  function pitch(shots, title, chosen='todos', suffix='') {
    const visible = (shots || []).filter(x => chosen==='todos' || (chosen==='errada'?shotKind(x)==='outra':shotKind(x)===chosen));
    const dots = visible.slice(0,400).map(s => {
      const position = shotPosition(s);
      if (!position) return '';
      const tip = [s.jogador, s.tipo_evento, s.minuto != null ? `${s.minuto}'` : null].filter(Boolean).join(' · ');
      return `<span class="shot-dot stats-shot ${shotKind(s)}" style="left:${position.left}%;top:${position.top}%" title="${esc(tip)}" role="img" aria-label="${esc(tip)}"></span>`;
    }).join('');
    const chip = (name, title) => `<button type="button" class="chip-btn ${chosen===name?'on':''}" data-df-map-filter="${name}" aria-pressed="${chosen===name}">${title}</button>`;
    return `<div class="fin-map-card df-premium-map" data-df-map-title="${esc(title)}">
      <div class="fin-map-head"><strong>${esc(title)}</strong><div class="fin-legend"><span><i class="lg gol"></i> Gol</span><span><i class="lg certa"></i> Certa</span><span><i class="lg outra"></i> Errada</span></div></div>
      <div class="fin-filtros modo-toggle">${chip('todos','Todas')}${chip('gol','Gols')}${chip('certa','Certas')}${chip('errada','Erradas')}</div>
      <div class="pitch-wrap stats-pitch"><div class="pitch-lines"><div class="halfway"></div><div class="circle"></div><div class="box top"></div><div class="box bottom"></div></div>${dots || '<div class="empty df-pitch-empty">Nenhuma finalização com coordenadas.</div>'}</div>
      <div class="fin-map-note">${compact(visible.length)} finalizações ${suffix} · ${dots?'Exibindo até 400 no mapa':'Sem posições disponíveis'}</div>
    </div>`;
  }

  async function chooseOriginalClub(id, row) {
    const panel = $('#painel');
    if (!panel || !panel.contains(row) || !id) return;
    const token = ++seq;
    originalMapId = id;
    originalMapFilter = 'todos';
    panel.querySelectorAll('#tbl-fin-clube .fin-row').forEach(el => el.classList.toggle('row-on', Number(el.dataset.clube)===id));
    const map = panel.querySelector('.fin-map-card');
    if (map) map.setAttribute('aria-busy','true');
    const hint = panel.querySelector('.fin-hint');
    if (hint) hint.textContent = 'Mapa de finalizações realizadas: ' + labelOfClub(id);
    try {
      const query = withScope({escopo:'mapa',clube_id:id}).toString();
      const key = `/api/stats/finalizacoes?${query}`;
      let result = mapCache.get(key);
      if (!result) { result = await json(key); mapCache.set(key,result); }
      if (token !== seq || !$('#tbl-fin-clube') || !panel.isConnected) return;
      originalMapShots = result.mapa || [];
      const current = panel.querySelector('.fin-map-card');
      if (current) current.outerHTML = pitch(originalMapShots, labelOfClub(id),'todos','realizadas');
    } catch(e) {
      if (token !== seq) return;
      const current = panel.querySelector('.fin-map-card');
      if (current) current.innerHTML = `<div class="error">${esc(e.message)}. Verifique a conexão.</div>`;
    }
  }

  // Captura o clique ANTES do handler legado. O clique no link do nome continua navegando.
  document.addEventListener('click', (ev) => {
    const filter = ev.target.closest('.df-premium-map [data-df-map-filter]');
    if (filter) {
      ev.stopPropagation(); ev.preventDefault();
      const selected = filter.dataset.dfMapFilter;
      const map = filter.closest('.df-premium-map');
      if (map.closest('#df-stats-custom')) {
        const shots = window.__dfShotsCustom || [];
        const title = map.dataset.dfMapTitle;
        map.outerHTML = pitch(shots,title,selected, mode === 'sofridas' ? 'sofridas' : 'realizadas');
      } else {
        originalMapFilter = selected;
        map.outerHTML = pitch(originalMapShots, labelOfClub(originalMapId),selected,'realizadas');
      }
      return;
    }
    const row = ev.target.closest('#tbl-fin-clube .fin-row[data-clube]');
    if (row && !ev.target.closest('a')) {
      // Somente no grupo finalizações realizadas, sem sobrescrever filtros nativos.
      ev.preventDefault(); ev.stopPropagation();
      chooseOriginalClub(Number(row.dataset.clube),row);
    }
    const btn = ev.target.closest('[data-df-stats-tab]');
    if (btn) {
      ev.preventDefault(); ev.stopPropagation();
      mode = btn.dataset.dfStatsTab;
      if (mode === 'sofridas') {sofridasState.page=1;sofridasState.selected=null;}
      ++seq;
      refreshTabs();
      if (mode !== 'realizadas') renderCustom();
    }
    if (ev.target.closest('#tabs-grupo [data-grupo], #tabs-main [data-tab]')) {
      mode = 'realizadas'; ++seq; window.__dfShotsCustom = [];
    }
  }, true);

  function refreshTabs() {
    const group = $('#tabs-grupo');
    if (!group || !group.isConnected) return;
    const fin = group.querySelector('[data-grupo="finalizacoes"]');
    if (!fin) return;
    fin.textContent = 'Finalizações Realizadas';
    const items = [['sofridas','Finalizações Sofridas'],['gols','Gols']];
    for (const [key, title] of items) {
      if (!group.querySelector(`[data-df-stats-tab="${key}"]`)) {
        const b = document.createElement('button');
        b.type='button'; b.className='tab df-stats-mode';b.dataset.dfStatsTab=key;b.textContent=title;
        b.setAttribute('aria-label',title);
        const last = group.querySelector('[data-df-stats-tab="sofridas"]') || fin;
        last.insertAdjacentElement('afterend',b);
      }
    }
    const customActive = mode !== 'realizadas';
    const panel = $('#painel');
    panel?.classList.toggle('df-shots-custom-active', customActive);
    panel?.querySelectorAll(':scope > .section:not(#df-stats-custom)').forEach(section => { section.hidden = customActive; });
    $('#painel .filters-right')?.classList.toggle('df-native-hidden', customActive);
    fin.classList.toggle('active',!customActive && fin.dataset.grupo === 'finalizacoes' && fin.classList.contains('active'));
    if (customActive) group.querySelectorAll('[data-grupo]').forEach(b=>b.classList.remove('active'));
    group.querySelectorAll('[data-df-stats-tab]').forEach(b=> {
      const on=b.dataset.dfStatsTab===mode;b.classList.toggle('active',on);b.setAttribute('aria-pressed',String(on));
    });
  }

  function header(title, description) {
    const id=getTeamId();
    const selector='<div class="df-shots-scope-note" role="note"><strong>'+(
      id?'Clube: '+esc(labelOfClub(id)):'Todos os clubes'
    )+'</strong><span>Use os filtros principais acima.</span></div>';
    return '<div class="df-shots-head"><div><h2>'+esc(title)+'</h2><p class="muted">'+esc(description)+'</p></div>'+selector+'</div>';
  }
  const wait = (message) => `<div class="df-shots-loading" role="status"><div class="df-shots-loader" aria-hidden="true"></div><span>${esc(message)}</span></div>`;
  const blank = `<div class="df-shots-empty"><h3>Escolha um clube</h3><p>Selecione o clube para consultar as finalizações e gols de seus jogos registrados.</p></div>`;

  async function loadTeam(id, updateProgress, currentSeq) {
    const q = withScope({aba:'jogos'});
    const key = `${id}|${q}`;
    if (teamCache.has(key)) return teamCache.get(key);
    const data = await json(`/api/clube/${id}?${q}`);
    const rawMatches = Array.isArray(data?.jogos?.linhas) ? data.jogos.linhas : [];
    const countryFilter = scope().pais;
    const allowed = countryFilter ? new Set([...($('#sel-liga')?.options || [])].map(o=>Number(o.value)).filter(Boolean)) : null;
    const matches = allowed ? rawMatches.filter(m=>allowed.has(Number(m.campeonato_id))) : rawMatches;
    if (!matches.length) {
      const empty={matches:[], detail:[]};teamCache.set(key,empty);return empty;
    }
    const details = new Array(matches.length);
    let next=0, finished=0;
    const concurrency=Math.min(4,matches.length);
    const workers=Array.from({length:concurrency}, async () => {
      while(next<matches.length) {
        if (currentSeq !== seq) return;
        const index=next++;const match=matches[index];
        const mid=Number(match.id);
        try {
          let promise=detailCache.get(mid);
          if(!promise){ promise=json(`/api/jogo/${mid}`);detailCache.set(mid,promise); }
          details[index]=await promise;
        } catch(e) {
          detailCache.delete(mid);
          details[index]={_failed:true, id:mid};
        }
        finished++;
        if (currentSeq===seq) updateProgress?.(finished,matches.length);
      }
    });
    await Promise.all(workers);
    if (currentSeq!==seq) return null;
    const result={matches,detail:details.filter(Boolean)};
    // Se alguma partida falhou, não gravar a coleção parcial no cache.
    if (!result.detail.some(d=>d._failed)) teamCache.set(key,result);
    return result;
  }
  function metrics(items, games) {
    const chutes=items.length;
    const goals=items.filter(isGoal).length;
    const on=items.filter(s => isGoal(s) || isSave(s)).length;
    return `<div class="df-shots-kpis"><article class="df-shot-kpi"><span>Finalizações</span><strong>${compact(chutes)}</strong><small>${games ? (chutes/games).toLocaleString('pt-BR',{maximumFractionDigits:2}) : '—'} por jogo</small></article><article class="df-shot-kpi"><span>No alvo</span><strong>${compact(on)}</strong><small>${pct(on,chutes)} das tentativas</small></article><article class="df-shot-kpi"><span>Gols</span><strong>${compact(goals)}</strong><small>${pct(goals,chutes)} de conversão</small></article><article class="df-shot-kpi"><span>Partidas</span><strong>${compact(games)}</strong><small>Com detalhes consultados</small></article></div>`;
  }
  function shotTable(items, against = false) {
    if (!items.length) return '<p class="empty">Não há finalizações neste período.</p>';
    const byPlayer = new Map();
    items.forEach(s=>{
      const key=`${s.jogador_id ?? s.jogador ?? '?'}|${s.clube_id ?? 0}`;
      const p=byPlayer.get(key)||{name:s.jogador||'Não informado',clube:s.clube||'—',shots:0,goals:0};
      p.shots++;if(isGoal(s))p.goals++;byPlayer.set(key,p);
    });
    const leaders=[...byPlayer.values()].sort((a,b)=>b.shots-a.shots).slice(0,15);
    return `<div class="table-wrap"><table class="data-table df-shots-table"><thead><tr><th>${against?'Adversário / Jogador':'Jogador'}</th>${against?'<th>Clube</th>':''}<th>Chutes</th><th>Gols</th></tr></thead><tbody>${leaders.map(p=>`<tr><td>${esc(p.name)}</td>${against?`<td>${esc(p.clube)}</td>`:''}<td>${compact(p.shots)}</td><td>${compact(p.goals)}</td></tr>`).join('')}</tbody></table></div>`;
  }

  const CATEGORIES = [
    ['individual','Jogador individual'],['parada','Bola parada'],['direito','Pé direito'],
    ['esquerdo','Pé esquerdo'],['cabeca','Cabeça'],['escanteio','Escanteio'],
    ['falta','Falta'],['penalti','Pênalti'],['origemDireita','Origem pela direita'],
    ['origemEsquerda','Origem pela esquerda'],['origemCentro','Origem pelo centro'],
  ];
  function goalTags(s) {
    const situ=normalize(s.situacao_jogada || s.tipo_jogada || s.situacao || '');
    const tipo=normalize(s.tipo_finalizacao || s.parte_corpo || s.parte_do_corpo || '');
    const origem=normalize(s.lado_jogada || s.origem_jogada || s.origem_ataque || s.lado_ataque || '');
    const tags=[];
    if (/individual|solo/.test(situ)) tags.push('individual');
    if (/bolaparada|setpiece|setplay|escanteio|corner|freekick|falta|penalti|penalty/.test(situ)) tags.push('parada');
    if (/rightfoot|pedireit|direito|footright/.test(tipo)) tags.push('direito');
    if (/leftfoot|peesquerd|esquerdo|footleft/.test(tipo)) tags.push('esquerdo');
    if (/header|cabeca|head/.test(tipo)) tags.push('cabeca');
    if (/corner|escanteio/.test(situ)) tags.push('escanteio');
    if (/freekick|tirolivre|cobrancadefalta|faltadireta|faltaindireta/.test(situ)) tags.push('falta');
    if (/penalti|penalty|penalt/.test(situ)) tags.push('penalti');
    // Direção da jogada não é a direção do chute: só classificar com um campo de origem explícito.
    if (/direit|right/.test(origem)) tags.push('origemDireita');
    if (/esquerd|left/.test(origem)) tags.push('origemEsquerda');
    if (/centro|central|center|middle/.test(origem)) tags.push('origemCentro');
    return tags;
  }
  function renderGoals(goals, games, clubs = []) {
    const numbers = Object.fromEntries(CATEGORIES.map(([k])=>[k,0]));
    let unclassified=0, contra=0;
    for(const goal of goals) {
      if(goalAgainst(goal)) contra++;
      const tags=goalTags(goal);
      if(!tags.length) unclassified++;
      tags.forEach(k=>numbers[k]++);
    }
    const isAll = clubs.length > 0;
    const scorers = new Map();
    for (const goal of goals) {
      const name = goalAgainst(goal) ? 'Gol contra do adversário' : (goal.jogador || 'Jogador não informado');
      const club = goal._clubName || '—';
      const key = isAll ? `${club}|${name}` : name;
      const item = scorers.get(key) || {name, club, count:0};
      item.count++;
      scorers.set(key,item);
    }
    const scorerRows = [...scorers.values()].sort((a,b) => b.count-a.count || a.name.localeCompare(b.name,'pt-BR'));
    const scorersTable = `<h3>Gols por jogador</h3><div class="table-wrap"><table class="data-table df-shots-table"><thead><tr><th>Jogador</th>${isAll?'<th>Clube</th>':''}<th>Gols</th></tr></thead><tbody>${scorerRows.map(item=>`<tr><td>${esc(item.name)}</td>${isAll?`<td>${esc(item.club)}</td>`:''}<td>${compact(item.count)}</td></tr>`).join('') || `<tr><td colspan="${isAll?3:2}">Sem gols no período.</td></tr>`}</tbody></table></div>`;
    const ranking = isAll ? `<h3>Gols por clube</h3><p class="muted df-shots-explain">Todos os clubes do filtro principal, inclusive os que não marcaram no período.</p><div class="table-wrap"><table class="data-table df-shots-table"><thead><tr><th>Clube</th><th>Jogos</th><th>Gols</th><th>Gols/jogo</th></tr></thead><tbody>${clubs.slice().sort((a,b)=>b.goals-a.goals || a.name.localeCompare(b.name,'pt-BR')).map(c=>`<tr><td>${esc(c.name)}</td><td>${compact(c.games)}</td><td><strong>${compact(c.goals)}</strong></td><td>${c.games?(c.goals/c.games).toLocaleString('pt-BR',{maximumFractionDigits:2}):'—'}</td></tr>`).join('')}</tbody></table></div>` : '';
    const kindCards=CATEGORIES.map(([key,name])=>`<article class="df-goal-type"><span>${name}</span><strong>${compact(numbers[key])}</strong><small>${pct(numbers[key],goals.length)}</small></article>`).join('');
    const rows = goals.slice().sort((a,b)=>String(b._date||'').localeCompare(String(a._date||''))).slice(0,100);
    return `<div class="df-shots-kpis"><article class="df-shot-kpi"><span>Gols marcados</span><strong>${compact(goals.length)}</strong><small>${games ? (goals.length/games).toLocaleString('pt-BR',{maximumFractionDigits:2}) : '—'} por jogo</small></article><article class="df-shot-kpi"><span>Com classificação disponível</span><strong>${compact(goals.length-unclassified)}</strong><small>${compact(unclassified)} sem categoria identificável</small></article><article class="df-shot-kpi"><span>Gols contra a favor</span><strong>${compact(contra)}</strong><small>Incluídos no total de gols</small></article></div>
    <h3>Tipos de gol</h3><p class="muted df-shots-explain">As categorias podem se sobrepor (ex.: pênalti + pé direito + bola parada). Nenhuma categoria é presumida quando o campo não está preenchido.</p>
    <div class="df-goal-types">${kindCards}</div>
    ${ranking}
    ${scorersTable}
    <h3>Últimos gols</h3><div class="table-wrap"><table class="data-table df-shots-table"><thead><tr><th>Data</th>${isAll?'<th>Clube</th>':''}<th>Jogador</th><th>Tipo identificado</th><th>Min.</th></tr></thead><tbody>${rows.map(g=>{
      const tags=goalTags(g).map(k=>CATEGORIES.find(c=>c[0]===k)?.[1]).filter(Boolean);
      return `<tr><td>${esc(g._date?.slice(0,10)||'—')}</td>${isAll?`<td>${esc(g._clubName||'—')}</td>`:''}<td>${esc(goalAgainst(g)?'Gol contra a favor':g.jogador||'—')}</td><td>${esc(tags.join(' · ')||'Não informado')}</td><td>${esc(g.minuto??'—')}</td></tr>`;
    }).join('')||`<tr><td colspan="${isAll?5:4}">Sem gols no período.</td></tr>`}</tbody></table></div>`;
  }

  async function renderAllGoals(body, token) {
    const options = [...($('#sel-clube')?.options || [])]
      .filter(o => positive(o.value));
    const ids = [...new Map(options.map(o => [Number(o.value), o.textContent.trim()])).entries()];
    if (!ids.length) {
      body.innerHTML = '<div class="df-shots-empty"><h3>Nenhum clube no filtro atual</h3><p>Escolha outro campeonato, país ou temporada nos filtros acima.</p></div>';
      return;
    }
    body.innerHTML = wait(`Consultando 0 de ${ids.length} clubes…`);
    const clubs = new Array(ids.length);
    const goalsByClub = new Array(ids.length);
    let cursor=0, completed=0, failedMatches=0, failedClubs=0;
    const workers=Array.from({length:Math.min(3,ids.length)}, async ()=>{
      while (cursor < ids.length && token === seq) {
        const index=cursor++;
        const [id,name]=ids[index];
        try {
          const data = await loadTeam(id, null, token);
          if (token!==seq || !data) return;
          const valid=data.detail.filter(d=>!d._failed);
          failedMatches+=data.detail.length-valid.length;
          const goals=valid.flatMap(game=>{
            const date=game.data || data.matches.find(m=>Number(m.id)===Number(game.id))?.data || '';
            return (Array.isArray(game.finalizacoes)?game.finalizacoes:[])
              .filter(shot=>goalForTeam(shot,id))
              .map(shot=>({...shot,_date:date,_clubName:name,_clubId:id}));
          });
          clubs[index]={id,name,games:valid.length,goals:goals.length};
          goalsByClub[index]=goals;
        } catch(e) {
          failedClubs++;
          clubs[index]={id,name,games:0,goals:0,failed:true};
          goalsByClub[index]=[];
        }
        completed++;
        if (token===seq && body.isConnected) {
          const status=$('.df-shots-loading span',body);
          if (status) status.textContent=`Consultando clubes: ${completed} de ${ids.length}`;
        }
      }
    });
    await Promise.all(workers);
    if (token!==seq || !body.isConnected) return;
    const successful=clubs.filter(c=>c && !c.failed);
    const goals=goalsByClub.flatMap(list=>list || []);
    const appearances=successful.reduce((sum,c)=>sum+c.games,0);
    const warning=(failedClubs||failedMatches) ? `<p class="df-shots-warning" role="alert">Resultado parcial: ${compact(failedClubs)} clube(s) e ${compact(failedMatches)} partida(s) não puderam ser consultados. Esses clubes não entram no ranking.</p>` : '';
    body.innerHTML=warning+renderGoals(goals,appearances,successful);
  }


  function sufferedNumber(v, digits=0) {
    return v==null ? '—' : Number(v).toLocaleString('pt-BR', {minimumFractionDigits:digits,maximumFractionDigits:digits});
  }
  function sufferedTable(data,selected) {
    const showLeague=!$('#sel-liga')?.value;
    const columns=[['clube','Clube'],['jogos','J'],['chutes','Chutes'],['certas','Certas'],
      ['gols','Gols'],['dist_chute','Dist. chute (m)'],
      ['dist_certa','Dist. certa (m)'],['dist_gol','Dist. gol (m)']];
    const heading=([key,label])=>'<th scope="col"><button type="button" class="df-suffered-th" data-df-suffered-sort="'+key+'">'+esc(label)+(data.ordenar===key?(data.ordem==='asc'?' ↑':' ↓'):'')+'</button></th>';
    const rows=(data.linhas||[]).map((item,i)=>{
      const active=Number(item.clube_id)===selected;
      const photo=item.logo&&/^https?:\/\//.test(item.logo)
        ? '<img src="'+esc(item.logo)+'" alt="" loading="lazy" onerror="this.replaceWith(document.createTextNode(\'—\'))">'
        : '<span class="df-suffered-fallback" aria-hidden="true">'+esc(String(item.clube||'?').slice(0,1))+'</span>';
      return '<tr class="df-suffered-row '+(active?'row-on':'')+'" tabindex="0" role="button" aria-pressed="'+active+'" data-df-suffered-club="'+item.clube_id+'">'+
        '<td>'+((data.page-1)*data.page_size+i+1)+'</td>'+
        '<td class="df-suffered-image">'+photo+'</td>'+
        '<td class="df-suffered-name"><a href="/clube/'+item.clube_id+'">'+esc(item.clube)+'</a></td>'+
        (showLeague?'<td>'+esc(item.campeonato||'—')+'</td>':'')+
        '<td>'+sufferedNumber(item.jogos)+'</td>'+
        '<td>'+sufferedNumber(item.chutes)+'</td>'+
        '<td>'+sufferedNumber(item.certas)+'</td>'+
        '<td><strong>'+sufferedNumber(item.gols)+'</strong></td>'+
        '<td>'+sufferedNumber(item.dist_chute,1)+'</td>'+
        '<td>'+sufferedNumber(item.dist_certa,1)+'</td>'+
        '<td>'+sufferedNumber(item.dist_gol,1)+'</td></tr>';
    }).join('')||'<tr><td colspan="'+(showLeague?11:10)+'">Sem registros neste filtro.</td></tr>';
    return '<div class="table-wrap df-suffered-wrap"><table class="data-table df-suffered-table"><thead><tr>'+
      '<th scope="col">#</th><th scope="col">IMG</th>'+heading(columns[0])+
      (showLeague?'<th scope="col">Campeonato</th>':'')+columns.slice(1).map(heading).join('')+
      '</tr></thead><tbody>'+rows+'</tbody></table></div>';
  }
  function sufferedPagination(data) {
    if(Number(data.pages||1)<=1)return '';
    return '<nav class="df-suffered-pagination" aria-label="Paginação de finalizações sofridas">'+
      '<button type="button" data-df-suffered-page="'+(data.page-1)+'" '+(data.page<=1?'disabled':'')+'>Anterior</button>'+
      '<span>Página '+data.page+' de '+data.pages+' · '+compact(data.total)+' registros</span>'+
      '<button type="button" data-df-suffered-page="'+(data.page+1)+'" '+(data.page>=data.pages?'disabled':'')+'>Próxima</button></nav>';
  }
  async function renderSuffered(body,token) {
    body.innerHTML=wait('Carregando finalizações sofridas por clube…');
    try {
      const selected=getTeamId();
      const query=withScope({
        escopo:'clube',page:sofridasState.page,page_size:20,
        ordenar:sofridasState.ordenar,ordem:sofridasState.ordem,
        ...(selected?{clube_id:selected}:{})
      });
      const data=await json('/api/stats/finalizacoes-sofridas?'+query.toString());
      if(token!==seq||!body.isConnected||mode!=='sofridas')return;
      sofridasState.page=Number(data.page)||1;
      const ids=(data.linhas||[]).map(row=>Number(row.clube_id));
      const target=selected || (ids.includes(sofridasState.selected)?
        sofridasState.selected:(Number(data.mapa_clube_id)||ids[0]||null));
      sofridasState.selected=target;
      window.__dfShotsCustom=data.mapa||[];
      const mapTitle=labelOfClub(target)+' — finalizações sofridas';
      body.innerHTML='<div class="fin-layout df-suffered-layout"><div>'+
        sufferedTable(data,target)+sufferedPagination(data)+
        '<p class="fin-hint">'+(selected?'Mapa do clube escolhido no filtro principal.':'Clique em uma linha para atualizar o mapa.')+
        '</p></div><div id="df-suffered-map">'+pitch(data.mapa||[],mapTitle,'todos','sofridas')+'</div></div>';
      if(target&&Number(data.mapa_clube_id)!==target)await chooseSufferedClub(target,body);
    }catch(e){
      if(token===seq&&body.isConnected)body.innerHTML='<div class="error">Falha ao carregar finalizações sofridas: '+esc(e.message)+'</div>';
    }
  }
  async function chooseSufferedClub(id,body) {
    if(!id||mode!=='sofridas'||!body)return;
    const token=++seq;
    sofridasState.selected=id;
    body.querySelectorAll('.df-suffered-row').forEach(row=>{
      const active=Number(row.dataset.dfSufferedClub)===id;
      row.classList.toggle('row-on',active);
      row.setAttribute('aria-pressed',String(active));
    });
    const map=$('#df-suffered-map',body);
    if(map)map.innerHTML=wait('Atualizando mapa…');
    try {
      const q=withScope({escopo:'mapa',clube_id:id});
      const response=await json('/api/stats/finalizacoes-sofridas?'+q.toString());
      if(token!==seq||!map?.isConnected||mode!=='sofridas')return;
      window.__dfShotsCustom=response.mapa||[];
      map.innerHTML=pitch(response.mapa||[],labelOfClub(id)+' — finalizações sofridas','todos','sofridas');
    }catch(e){
      if(token===seq&&map?.isConnected)map.innerHTML='<div class="error">'+esc(e.message)+'</div>';
    }
  }
  document.addEventListener('click',ev=>{
    if(mode!=='sofridas')return;
    const sort=ev.target.closest('[data-df-suffered-sort]');
    if(sort){
      ev.preventDefault();
      const col=sort.dataset.dfSufferedSort;
      sofridasState.ordem=sofridasState.ordenar===col&&sofridasState.ordem==='desc'?'asc':'desc';
      sofridasState.ordenar=col;sofridasState.page=1;sofridasState.selected=null;
      renderCustom();return;
    }
    const page=ev.target.closest('[data-df-suffered-page]');
    if(page){
      ev.preventDefault();if(page.disabled)return;
      sofridasState.page=Number(page.dataset.dfSufferedPage)||1;
      sofridasState.selected=null;renderCustom();return;
    }
    const row=ev.target.closest('.df-suffered-row');
    if(row&&!ev.target.closest('a,button')){
      ev.preventDefault();
      chooseSufferedClub(Number(row.dataset.dfSufferedClub),$('#df-stats-custom .df-shots-result'));
    }
  });
  document.addEventListener('keydown',ev=>{
    if(mode!=='sofridas'||!['Enter',' '].includes(ev.key))return;
    const row=ev.target.closest('.df-suffered-row');
    if(!row)return;
    ev.preventDefault();
    chooseSufferedClub(Number(row.dataset.dfSufferedClub),$('#df-stats-custom .df-shots-result'));
  });
  async function renderCustom() {
    if(mode==='realizadas') return;
    const panel=$('#painel'), group=$('#tabs-grupo');
    if(!panel||!group) return;
    let root=$('#df-stats-custom');
    if(!root) {
      root=document.createElement('section');
      root.className='section df-shots-custom';root.id='df-stats-custom';
      const first=panel.querySelector('.section');
      if(first) first.before(root); else panel.appendChild(root);
    }
    refreshTabs();
    const title = mode === 'sofridas' ? 'Finalizações Sofridas' : 'Gols';
    const description = mode === 'sofridas' ? 'Chutes concedidos aos adversários nos jogos registrados.' : 'Gols marcados e suas características, conforme o registro disponível.';
    root.innerHTML=header(title,description);
    const body=document.createElement('div');body.className='df-shots-result';root.appendChild(body);
    const id=getTeamId();
    const token=++seq;
    if (mode==='sofridas') {
      await renderSuffered(body,token);
      return;
    }
    if (mode==='gols' && !id) {
      await renderAllGoals(body,token);
      return;
    }
    if(!id){body.innerHTML=blank;return;}
    body.innerHTML=wait('Consultando jogos de '+labelOfClub(id)+'…');
    try {
      const data=await loadTeam(id,(done,total)=>{
        if(token===seq && body.isConnected){
          const status=$('.df-shots-loading span',body);
          if(status) status.textContent=`Carregando detalhes das partidas: ${done} de ${total}`;
        }
      },token);
      if(!data||token!==seq||!body.isConnected) return;
      const failed=data.detail.filter(x=>x._failed).length;
      const valid=data.detail.filter(x=>!x._failed);
      const list=valid.flatMap(game=>{
        const date = game.data || data.matches.find(m=>Number(m.id)===Number(game.id))?.data || '';
        return (Array.isArray(game.finalizacoes)?game.finalizacoes:[]).map(s=>({...s,_date:date}));
      });
      const warning=failed ? `<p class="df-shots-warning" role="alert">Não foi possível carregar ${compact(failed)} partida(s). Os valores abaixo são parciais.</p>` : '';
      if(mode==='sofridas') {
        const suffered=list.filter(s=>Number(s.clube_id)!==id && !goalAgainst(s));
        window.__dfShotsCustom=suffered;
        body.innerHTML=warning+metrics(suffered,valid.length)+`<div class="df-shots-layout"><div><h3>Principais finalizadores adversários</h3>${shotTable(suffered,true)}</div>${pitch(suffered,`${labelOfClub(id)} — finalizações sofridas`,'todos','sofridas')}</div><p class="muted df-shots-footnote">O mapa representa tentativas dos adversários. Gols contra podem alterar o placar sem representar um chute do adversário.</p>`;
      } else {
        const goals=list.filter(s=>goalForTeam(s,id));
        window.__dfShotsCustom=[];
        body.innerHTML=warning+renderGoals(goals,valid.length);
      }
    }catch(e){
      if(token===seq&&body.isConnected)body.innerHTML=`<div class="error">Não foi possível consultar as partidas: ${esc(e.message)}</div>`;
    }
  }

  // Só acrescenta os botões aos subtabs já criados por stats.js.
  function ensureTabs() {
    const group=$('#tabs-grupo');
    if(!group) return;
    const hasAddon=Boolean(group.querySelector('[data-df-stats-tab="gols"]'));
    if (!hasAddon) {
      refreshTabs();
      if(mode!=='realizadas') renderCustom();
    }
    const panel=$('#painel');
    if(mode!=='realizadas' && panel && !panel.querySelector('#df-stats-custom')) renderCustom();
  }
  // O script legado substitui #painel com innerHTML depois de cada seleção/filtro.
  // Observação agendada evita alterações na mesma pilha de renderização.
  let frame=0;
  const observer=new MutationObserver(()=>{
    if(frame) return;
    frame=requestAnimationFrame(()=>{frame=0;ensureTabs();});
  });
  observer.observe(document.documentElement,{childList:true,subtree:true});
  ensureTabs();
  document.addEventListener('DOMContentLoaded', ensureTabs);
})();