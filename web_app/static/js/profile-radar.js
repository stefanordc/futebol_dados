/** Dados Futebol — Radar de perfil. Sem alterações no backend e sem bibliotecas externas.
 * Índices heurísticos de 0 a 100, com referências fixas de desempenho por jogo.
 */
(() => {
  'use strict';
  if (window.__dfProfileRadar) return;
  window.__dfProfileRadar = true;

  const $ = (q, root = document) => root.querySelector(q);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' })[c]);
  const number = (x) => x === undefined || x === null || x === '' || !Number.isFinite(Number(x)) ? null : Number(x);
  const clamp = (n, lo=0, hi=100) => Math.max(lo, Math.min(hi, n));
  const score = (actual, benchmark) => actual == null ? null : Math.round(clamp(actual / benchmark * 100));
  const inverse = (actual, worst) => actual == null ? null : Math.round(clamp((1 - actual / worst) * 100));
  const mean = (...values) => { const xs=values.filter(x=>x!=null&&Number.isFinite(x)); return xs.length ? xs.reduce((a,b)=>a+b,0)/xs.length : null; };
  const divide = (num, den) => num == null || den == null || den <= 0 ? null : num/den;
  const fmt = (v,d=1) => v == null ? '—' : Number(v).toLocaleString('pt-BR',{maximumFractionDigits:d});
  const exists = (obj,key) => Object.prototype.hasOwnProperty.call(obj||{},key) && number(obj[key])!==null;
  const combine = (...scores) => {const v=mean(...scores);return v===null?null:Math.round(clamp(v));};
  const maxFetches=100;
  const cache=new Map();
  let renderKey='', sequence=0, frame=0;
  const idInUrl = Number(location.pathname.split('/').filter(Boolean).pop());
  const kind=location.pathname.startsWith('/clube/')?'clube':location.pathname.startsWith('/jogador/')?'jogador':location.pathname.startsWith('/tecnico/')?'tecnico':null;
  if(!kind||!Number.isInteger(idInUrl)||idInUrl<=0)return;

  async function get(url){
    if(cache.has(url))return cache.get(url);
    const promise=fetch(url).then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json();});
    cache.set(url,promise);
    try{return await promise;}catch(e){cache.delete(url);throw e;}
  }
  const scope = () => {
    const q = new URLSearchParams();
    const season = $(kind==='clube'?'#clube-temp':'#ent-temp')?.value;
    if(season)q.set('temporada',season);
    if(kind==='clube'){
      const league=$('#clube-camp')?.value;
      const mando=$('#clube-mando')?.value;
      if(league)q.set('campeonato_id',league);
      if(mando&&mando!=='todos')q.set('mando',mando);
    }
    return q;
  };
  const api = (which,params={})=>{
    const q=scope();Object.entries(params).forEach(([k,v])=>{if(v!=null)q.set(k,String(v));});
    return `/api/${which}/${idInUrl}?${q.toString().replace(/%2F/gi,'/')}`;
  };
  const per = (obj,key,games) => exists(obj,key) ? divide(number(obj[key]),games) : null;
  const metric = (line,key,category='media') => {
    const entry=line?.valores?.[key];
    return entry && number(entry[category])!=null ? number(entry[category]):null;
  };
  function sixTeam(obj){
    const {games, goalsFor, goalsAgainst, sheets, wins, draws, shots, xg, chances, blocks, intercepts, passes}=obj;
    const avgScored=divide(goalsFor,games), avgConceded=divide(goalsAgainst,games);
    const rate=(value,key)=>divide(value,number(obj[key+'Games'])??games);
    const shotPg=rate(shots,'shots'), xgPg=rate(xg,'xg'), chancesPg=rate(chances,'chances');
    const defenses=combine(score(rate(blocks,'blocks'),7),score(rate(intercepts,'intercepts'),13));
    const winRate=divide(wins*3+draws,3*games);
    const prevent=inverse(avgConceded,2.8);
    return [
      combine(score(shotPg,18),score(xgPg,2.4)), // força ofensiva
      combine(prevent,defenses),                  // força defensiva
      combine(score(xgPg,2.4),score(chancesPg,4.0),score(rate(passes,'passes'),570)),
      score(avgScored,3.0),
      combine(prevent,score(divide(sheets,games),0.65)),
      combine(score(divide(goalsFor,shots),0.23),score(winRate,0.85)),
    ];
  }
  const CLUB_LABELS=['Ataque','Defesa','Criatividade','Gols','Evitar gols','Eficiência'];
  const CLUB_NOTES=[
    'Volume de chutes e xG por partida',
    'Gols sofridos e ações defensivas por partida',
    'xG, chances e passes por partida',
    'Gols marcados por partida',
    'Gols sofridos (inverso) e jogos sem sofrer gols',
    'Conversão de chutes e aproveitamento de pontos',
  ];
  function extractStats(stats,id){
    const row=(stats?.linhas||[]).find(x=>Number(x.clube_id)===id) || (stats?.linhas||[])[0];
    return row||{};
  }
  async function clubRadar(){
    const [general,att,def,passes] = await Promise.all([
      get(api('clube',{aba:'geral'})),
      get(api('clube',{aba:'estatisticas',grupo:'ataque'})),
      get(api('clube',{aba:'estatisticas',grupo:'defesa'})),
      get(api('clube',{aba:'estatisticas',grupo:'passes'})),
    ]);
    const t=general.geral?.total||{};
    const games=number(t.jogos)||0;
    const a=extractStats(att.estatisticas,idInUrl), d=extractStats(def.estatisticas,idInUrl), p=extractStats(passes.estatisticas,idInUrl);
    const vals=sixTeam({
      games,goalsFor:number(t.gols_marcados),goalsAgainst:number(t.gols_sofridos),
      sheets:number(t.clean_sheets),wins:number(t.v)||0,draws:number(t.e)||0,
      shots:metric(a,'total_chutes','soma'),shotsGames:number(a.jogos),
      xg:metric(a,'xg','soma'),xgGames:number(a.jogos),
      chances:metric(a,'grandes_chances','soma'),chancesGames:number(a.jogos),
      blocks:metric(d,'bloqueios','soma'),blocksGames:number(d.jogos),
      intercepts:metric(d,'interceptacoes','soma'),interceptsGames:number(d.jogos),
      passes:metric(p,'passes_certos','soma'),passesGames:number(p.jogos),
    });
    return {title:'Perfil de desempenho do clube',subtitle:`${games} jogos no recorte selecionado · índices de 0 a 100`,labels:CLUB_LABELS,values:vals,notes:CLUB_NOTES,warning:games<5?'Amostra pequena: menos de cinco jogos.':null};
  }

  const PLAYER_LABELS=['Finalização','Criação','Drible','Desarme','Interceptação','Duelos'];
  const PLAYER_NOTES=[
    'Precisão de chutes: chutes no alvo divididos pelo total de chutes. Valor 100 apenas quando todas as finalizações foram no alvo.',
    'Assistências, chances criadas e xA por 90 minutos',
    'Dribles certos por 90 minutos e taxa de sucesso',
    'Desarmes e ações defensivas por 90 minutos',
    'Interceptações e recuperações por 90 minutos',
    'Duelos ganhos por 90 minutos e percentual vencido',
  ];
  async function playerRadar(){
    const data=await get(api('jogador'));
    const est=data.estatisticas||{};
    const minutes=number(est.minutos)||0, units=minutes/90;
    const all=Object.values(est.metricas||{}).flat();
    const vals=Object.fromEntries(all.map(x=>[x.chave,x]));
    const sum=(k)=>vals[k] ? number(vals[k].soma):null;
    const per90=(k)=>divide(sum(k),units);
    const pGoals=per90('gols'),shots=per90('chutes_certos'),xg=per90('xg');
    const attempts=sum('chutes_total'),onTarget=sum('chutes_certos');
    // Precisão real: 100 somente se todas as tentativas registradas foram no alvo.
    const finishing=attempts!=null&&attempts>0&&onTarget!=null ? Math.round(clamp(100*onTarget/attempts)) : null;
    const pAs=per90('assistencias'), chances=per90('chances_criadas'), xa=per90('xa');
    const dr=per90('dribles_certos'), att=per90('dribles');
    const tackles=per90('desarmes'),defActions=per90('acoes_defensivas');
    const intercepts=per90('interceptacoes'),recoveries=per90('recuperacao_posse_bola');
    const duels=per90('disputas_ganhas');
    const attempted=(sum('disputas_chao')||0)+(sum('disputas_aereas')||0);
    const won=(sum('disputas_chao_ganhas')||0)+(sum('disputas_aereas_ganhas')||0);
    const ratio=attempted>0?won/attempted:null;
    const scores=[
      finishing,
      combine(score(pAs,0.5),score(chances,3.5),score(xa,0.65)),
      combine(score(dr,5.5),score(divide(dr,att),0.75)),
      combine(score(tackles,4.8),score(defActions,10)),
      combine(score(intercepts,3.5),score(recoveries,8)),
      combine(score(duels,12),score(ratio,0.7)),
    ];
    let warning=null;
    if(minutes<450)warning='Amostra pequena: menos de 450 minutos. As notas podem oscilar bastante.';
    return {title:'Atributos do jogador — 3 ofensivos e 3 defensivos',subtitle:`${fmt(minutes,0)} min jogados · valores normalizados por 90 minutos`,labels:PLAYER_LABELS,values:scores,notes:PLAYER_NOTES,warning};
  }

  function coachMatchStats(detail,coachId){
    const side=Number(detail.tecnico_casa_id)===coachId?'Casa':Number(detail.tecnico_fora_id)===coachId?'Fora':null;
    if(!side)return null;
    const c=side==='Casa'?'Fora':'Casa';
    const gf=number(detail[side==='Casa'?'gols_casa':'gols_fora']);
    const ga=number(detail[side==='Casa'?'gols_fora':'gols_casa']);
    const e=detail.estatisticas?.completo?.[side]||{};
    return {
      gf,ga, clean:ga===0?1:0,win:gf>ga?1:0,draw:gf===ga?1:0,
      shots:number(e.total_chutes),xg:number(e.xg),chances:number(e.grandes_chances),
      blocks:number(e.bloqueios),intercepts:number(e.interceptacoes),passes:number(e.passes_certos),
      poss:number(e.posse_bola),
    };
  }
  async function coachRadar(progress,token){
    const profile=await get(api('tecnico'));
    const lines=profile.linhas||[];
    const clubs=[...new Map(lines.map(l=>[l.clube_id,l])).values()];
    if(!clubs.length)return {title:'Estilo de jogo do técnico',subtitle:'Sem jogos na temporada',labels:CLUB_LABELS,values:Array(6).fill(null),notes:CLUB_NOTES,warning:'Não há partidas registradas para o técnico.'};
    const matchDates=new Map();
    const clubJobs=clubs.map(async line=>{
      const q=new URLSearchParams({aba:'jogos'});
      if(profile.temporada)q.set('temporada',profile.temporada);
      const data=await get(`/api/clube/${line.clube_id}?${q}`);
      for(const m of data.jogos?.linhas||[])matchDates.set(Number(m.id),String(m.data||''));
    });
    await Promise.all(clubJobs);
    const all=[...matchDates.keys()].filter(Boolean).sort((a,b)=>matchDates.get(b).localeCompare(matchDates.get(a)) || b-a);
    // Seleção de amostra limitada para proteger o backend. O número é informado no cartão.
    const candidates=all.slice(0,maxFetches);
    let pos=0,done=0,fail=0;
    const own=[];
    await Promise.all(Array.from({length:4},async()=>{
      while(pos<candidates.length && token===sequence){
        const id=candidates[pos++];
        try{
          const detail=await get(`/api/jogo/${id}`);
          const m=coachMatchStats(detail,idInUrl);
          if(m)own.push(m);
        }catch{fail++;}
        done++;
        if(done%5===0)progress?.(`Verificando partidas do técnico: ${done}/${candidates.length}`);
      }
    }));
    if(token!==sequence)return null;
    const games=own.length;
    const sum=(k)=>{const xs=own.map(x=>x[k]).filter(x=>x!=null);return xs.length?xs.reduce((a,b)=>a+b,0):null;};
    const vals=sixTeam({games,goalsFor:sum('gf'),goalsAgainst:sum('ga'),sheets:sum('clean'),wins:sum('win')||0,draws:sum('draw')||0,shots:sum('shots'),shotsGames:own.filter(m=>m.shots!=null).length,xg:sum('xg'),xgGames:own.filter(m=>m.xg!=null).length,chances:sum('chances'),chancesGames:own.filter(m=>m.chances!=null).length,blocks:sum('blocks'),blocksGames:own.filter(m=>m.blocks!=null).length,intercepts:sum('intercepts'),interceptsGames:own.filter(m=>m.intercepts!=null).length,passes:sum('passes'),passesGames:own.filter(m=>m.passes!=null).length});
    const offensive=combine(vals[0],vals[2],vals[3]);
    const defensive=combine(vals[1],vals[4]);
    let style='Indeterminado',description='Os dados disponíveis não permitem distinguir o estilo.';
    if(offensive!=null && defensive!=null){
      const d=offensive-defensive;
      style=d>=12?'Predominantemente ofensivo':d<=-12?'Predominantemente defensivo':'Equilibrado';
      description=`Índice ofensivo ${offensive}/100 · defensivo ${defensive}/100. Diferença ${d>0?'+':''}${d} pontos. É uma estimativa estatística, não uma identificação da tática.`;
    }
    return {title:'Estilo de jogo do técnico',subtitle:`${games} partidas confirmadas sob seu comando`,labels:CLUB_LABELS,values:vals,notes:CLUB_NOTES,
      style,description,
      warning:[all.length>maxFetches?`Amostra limitada às ${maxFetches} partidas candidatas mais recentes.`:null,fail?`${fail} partidas não puderam ser consultadas.`:null,games<5?'Amostra pequena (menos de cinco partidas).':null].filter(Boolean).join(' ')};
  }
  const SPECIAL_LABELS=[
    'Força ofensiva','Força defensiva','Bola parada ofensiva',
    'Bola parada defensiva','Bola aérea ofensiva','Bola aérea defensiva'
  ];
  const SPECIAL_NOTES=[
    'Volume ofensivo e qualidade das chances por jogo',
    'Gols sofridos e ações defensivas por jogo',
    'xG de jogada ensaiada e gols identificados em bola parada, por jogo',
    'Gols em bola parada sofridos (menor é melhor); apenas lances identificados',
    'Gols de cabeça e duelos aéreos ganhos (duelos como indicador complementar)',
    'Gols de cabeça sofridos e aproveitamento geral em duelos aéreos'
  ];
  const normal=(s)=>String(s??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]/g,'');
  const goal=(shot)=>/gol|goal/.test(normal(shot?.tipo_evento));
  const ownGoal=(shot)=>shot?.foi_gol_contra===true||shot?.foi_gol_contra===1||shot?.foi_gol_contra==='true';
  const setPiece=(shot)=>/escanteio|corner|bolaparada|setpiece|falta|freekick|penalt/.test(normal(shot?.situacao_jogada||shot?.situacao||''));
  const headerGoal=(shot)=>/cabeca|header|head/.test(normal(shot?.tipo_finalizacao||''));
  async function clubSpecialRadar(primary,progress,token){
    const [attack,defense,matchesResponse] = await Promise.all([
      get(api('clube',{aba:'estatisticas',grupo:'ataque'})),
      get(api('clube',{aba:'estatisticas',grupo:'defesa'})),
      get(api('clube',{aba:'jogos'})),
    ]);
    const attackRow=extractStats(attack.estatisticas,idInUrl);
    const defenseRow=extractStats(defense.estatisticas,idInUrl);
    const plays=matchesResponse?.jogos?.linhas||[];
    const limited=plays.slice(0,80);
    let ptr=0,seen=0,failed=0;
    const details=[];
    await Promise.all(Array.from({length:Math.min(4,limited.length)},async()=>{
      while(ptr<limited.length&&token===sequence){
        const m=limited[ptr++];
        try{details.push(await get(`/api/jogo/${m.id}`));}
        catch{failed++;}
        seen++;
        if(seen%10===0)progress?.(`Avaliando bola parada e jogo aéreo: ${seen}/${limited.length}`);
      }
    }));
    if(token!==sequence)return null;
    const samples=details.length;
    let forSet=0,againstSet=0,forHeaders=0,againstHeaders=0,classified=0;
    for(const game of details){
      for(const shot of game.finalizacoes||[]){
        if(!goal(shot))continue;
        const team=Number(shot.clube_id);
        const forUs=ownGoal(shot)?team!==idInUrl:team===idInUrl;
        const situ=shot.situacao_jogada||shot.situacao;
        if(situ)classified++;
        if(setPiece(shot)){if(forUs)forSet++;else againstSet++;}
        if(headerGoal(shot)){if(forUs)forHeaders++;else againstHeaders++;}
      }
    }
    const aerial=metric(defenseRow,'disputas_aereas_ganhas','soma');
    const attempts=metric(defenseRow,'disputas_aereas','soma');
    const aerialRate=divide(aerial,attempts);
    const aerialPG=divide(aerial,number(defenseRow.jogos));
    const xgSet=metric(attackRow,'xg_jogada_ensaiada','soma');
    const xgSetRate=divide(xgSet,number(attackRow.jogos));
    // Sem classificação explícita, NÃO supor gols de bola parada = zero.
    const setOff=combine(score(xgSetRate,.55),classified?score(divide(forSet,samples),.65):null);
    const setDef=classified?inverse(divide(againstSet,samples),.65):null;
    const aerialOff=combine(score(aerialPG,13),classified?score(divide(forHeaders,samples),.35):null);
    const aerialDef=combine(score(aerialRate,.72),classified?inverse(divide(againstHeaders,samples),.35):null);
    const first=primary?.values||[];
    return {
      title:'Força por fundamento', subtitle:`${samples} partidas analisadas · referência relativa de 0 a 100`,
      labels:SPECIAL_LABELS,
      values:[first[0]??null,first[1]??null,setOff,setDef,aerialOff,aerialDef],
      notes:SPECIAL_NOTES,
      warning:[
        'Os atributos de bola parada e bola aérea usam os campos registrados e aproximações de duelos; não são medições oficiais.',
        !classified?'Não há classificação de situação dos gols suficiente para avaliar a bola parada defensiva.':null,
        failed?`${failed} partidas indisponíveis.`:null,
        plays.length>limited.length?`Amostra limitada às ${limited.length} partidas mais recentes.`:null,
      ].filter(Boolean).join(' ')
    };
  }
  function point(i,value,radius,center=210){
    const angle=-Math.PI/2+i*Math.PI/3,rad=radius*value;
    return {x:center+Math.cos(angle)*rad,y:center+Math.sin(angle)*rad};
  }
  function radarSvg(labels,values){
    const grid=[.25,.5,.75,1].map(scale=>{
      const points=labels.map((_,i)=>point(i,scale,140));
      return `<polygon points="${points.map(p=>`${p.x},${p.y}`).join(' ')}" fill="none" stroke="var(--radar-grid)" stroke-width="1"/>`;
    }).join('');
    const spokes=labels.map((_,i)=>{const p=point(i,1,140);return `<line x1="210" y1="210" x2="${p.x}" y2="${p.y}" stroke="var(--radar-grid)"/>`;}).join('');
    const labelsSvg=labels.map((label,i)=>{
      const p=point(i,1,180);const anchor=p.x<165?'end':p.x>255?'start':'middle';
      return `<text x="${p.x}" y="${p.y}" font-size="13" text-anchor="${anchor}" dominant-baseline="middle" fill="var(--text)">${esc(label)}</text>`;
    }).join('');
    const valid=values.every(v=>v!=null);
    const poly=valid?`<polygon points="${values.map((v,i)=>{const p=point(i,clamp(v)/100,140);return `${p.x},${p.y}`;}).join(' ')}" fill="var(--radar-fill)" stroke="var(--accent)" stroke-width="3" stroke-linejoin="round"/>`:'';
    const spots=values.map((v,i)=>{
      if(v==null)return '';
      const p=point(i,clamp(v)/100,140);
      return `<circle cx="${p.x}" cy="${p.y}" r="5" stroke="var(--bg-elev)" stroke-width="2" fill="var(--accent)"/>`;
    }).join('');
    return `<svg viewBox="0 0 420 420" class="df-profile-radar-svg" role="img" aria-label="Gráfico radar com seis atributos. ${esc(labels.map((name,i)=>`${name}: ${values[i]??'indisponível'}`).join('; '))}"><title>Radar de desempenho</title>${grid}${spokes}${poly}${spots}${labelsSvg}</svg>`;
  }
  function card(data,cardId="df-radar-card"){
    const valid=data.values.filter(x=>x!=null).length;
    const values=data.values.map(v=>v==null?'—':`${v}/100`);
    return `<section class="section df-radar-section" id="${cardId}" aria-labelledby="${cardId}-heading"><div class="df-radar-heading"><div><h2 class="section-title" id="${cardId}-heading">${esc(data.title)}</h2><p class="muted">${esc(data.subtitle)}</p></div><span class="df-radar-tag">Índice estimado · não oficial</span></div>
    ${data.style?`<div class="df-coach-style"><strong>${esc(data.style)}</strong><p>${esc(data.description)}</p></div>`:''}
    ${data.warning?`<p class="df-radar-warning">${esc(data.warning)}</p>`:''}
    <div class="df-radar-layout"><div>${radarSvg(data.labels,data.values)}</div><div class="df-radar-measures">${data.labels.map((name,i)=>`<div class="df-radar-metric" title="${esc(data.notes[i])}"><div class="df-radar-metric-line"><span>${i+1}. ${esc(name)}</span><strong>${values[i]}</strong></div><div class="df-radar-track"><span style="width:${data.values[i]??0}%"></span></div><small>${esc(data.notes[i])}</small></div>`).join('')}</div></div>
    <p class="df-radar-method">${valid}/6 eixos com dados. Normalização com referências fixas por partida (jogadores: por 90 min), limitada a 0–100. Indicadores ausentes ficam como “—” e não entram na área preenchida. Não é pontuação oficial do FIFA nem previsão de resultado.</p></section>`;
  }
  function mount(){
    const root=$('#conteudo'),header=root?.querySelector('.entity-header');
    if(!header)return;
    const clubPanel=kind==='clube'?$('#clube-painel'):null;
    const personSlot=kind!=='clube'?$('#df-profile-radar-slot'):null;
    if(kind!=='clube'&&!personSlot){const old=$('#df-profile-radar');if(old)old.remove();renderKey='';++sequence;return;}
    const onGeneral=kind!=='clube'||Boolean($('#clube-tabs [data-aba="geral"].active'));
    let node=$('#df-profile-radar');
    if(kind==='clube'&&(!onGeneral||!clubPanel)){
      if(node)node.remove();
      renderKey='';++sequence;
      return;
    }
    const q=scope(),sig=`${kind}:${idInUrl}?${q.toString()}`;
    if(node && renderKey===sig)return;
    renderKey=sig;
    const token=++sequence;
    if(!node){
      node=document.createElement('div');node.id='df-profile-radar';
      if(kind==='clube')clubPanel.append(node);
      else personSlot.append(node);
    }
    if(kind==='clube'){
      node.className='df-radar-pair';
      node.innerHTML='<div id="df-radar-main" class="df-radar-placeholder" role="status">Carregando radar de desempenho…</div><div id="df-radar-special" class="df-radar-placeholder" role="status">Carregando radar de fundamentos…</div>';
      const main=$('#df-radar-main',node),special=$('#df-radar-special',node);
      const progress=(msg)=>{if(token===sequence&&special?.isConnected)special.textContent=msg;};
      const first=clubRadar();
      first.then(data=>{
        if(token!==sequence||!main.isConnected)return;
        main.outerHTML=card(data,'df-radar-main');
      }).catch(e=>{
        if(token!==sequence||!main.isConnected)return;
        main.textContent=`Não foi possível calcular o radar: ${e.message}`;
        main.classList.add('error');
      });
      first.then(data=>clubSpecialRadar(data,progress,token)).then(data=>{
        if(token!==sequence||!special.isConnected||!data)return;
        special.outerHTML=card(data,'df-radar-special');
      }).catch(e=>{
        if(token!==sequence||!special.isConnected)return;
        special.textContent=`Fundamentos indisponíveis: ${e.message}`;
        special.classList.add('error');
      });
    }else{
      node.className='df-radar-single';
      node.innerHTML='<div class="df-radar-placeholder" role="status">Calculando perfil de desempenho…</div>';
      const progress=(msg)=>{if(token===sequence&&node.isConnected)node.textContent=msg;};
      const promise=kind==='jogador'?playerRadar():coachRadar(progress,token);
      Promise.resolve(promise).then(data=>{
        if(token!==sequence||!node.isConnected||!data)return;
        node.innerHTML=card(data,'df-radar-main');
      }).catch(e=>{
        if(token===sequence&&node.isConnected)node.innerHTML=`<div class="error">Não foi possível calcular o radar: ${esc(e.message)}</div>`;
      });
    }
  }
  const obs=new MutationObserver(()=>{if(frame)return;frame=requestAnimationFrame(()=>{frame=0;mount();});});
  obs.observe(document.documentElement,{childList:true,subtree:true});
  document.addEventListener('DOMContentLoaded',mount);
  mount();
})();
