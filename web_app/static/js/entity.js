import { openEditModal, pencilBtn } from "./edit.js";
import { setFavicon, setSiteFavicon } from "./favicon.js";
import { initNav } from "./nav.js";

const $ = (sel, el = document) => el.querySelector(sel);

function n(v, dig = 1) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("pt-BR", {
    minimumFractionDigits: dig,
    maximumFractionDigits: dig,
  });
}

function img(src, cls = "mini-av") {
  if (!src) return "";
  return `<img src="${src}" class="${cls}" alt="" loading="lazy" onerror="this.style.opacity=.25" />`;
}

const parts = location.pathname.split("/").filter(Boolean);
const tipo = parts[0]; // jogador | tecnico | arbitro
const id = Number(parts[1]);
const params = new URLSearchParams(location.search);

let state = {
  data: null,
  temporada: params.get("temporada") || null,
  grupo: params.get("grupo") || "resumo",
  modo: params.get("modo") === "media" ? "media" : "soma",
  aba: params.get("aba") || "geral",
  campeonatoFiltro: "",
  clubeFiltro: "",
};

const TIPO_API = { jogador: "jogador", tecnico: "tecnico", arbitro: "arbitro" };
const TIPO_EDIT = { jogador: "jogador", tecnico: "tecnico", arbitro: "arbitro" };

async function load() {
  const api = TIPO_API[tipo];
  if (!api) throw new Error("Tipo inválido");
  const q = new URLSearchParams();
  if (state.temporada) q.set("temporada", state.temporada);
  const res = await fetch(`/api/${api}/${id}?${q.toString().replace(/%2F/gi, "/")}`);
  if (!res.ok) {
    if (tipo !== "arbitro") throw new Error("Falha ao consultar perfil (HTTP " + res.status + ")");
    const fallback = await fetch("/api/stats/arbitros");
    if (!fallback.ok) throw new Error("Perfil do árbitro indisponível (HTTP " + res.status + ").");
    const dados = await fallback.json();
    const encontrado = (dados.itens || []).find(a => Number(a.id) === id);
    if (!encontrado) throw new Error("Árbitro não encontrado no ranking.");
    state.data = {tipo:"arbitro", entidade:encontrado, temporada:null, temporadas:[], linhas:[], fallback:true};
  } else state.data = await res.json();
  state.temporada = state.data.temporada;
  const grupos = state.data.estatisticas?.grupos || {};
  if (!grupos[state.grupo]) {
    state.grupo = Object.keys(grupos)[0] || "resumo";
  }
}

function syncUrl() {
  const q = new URLSearchParams();
  if (state.temporada) q.set("temporada", state.temporada);
  if (state.aba && state.aba !== "geral") q.set("aba", state.aba);
  if (tipo === "jogador") {
    if (state.grupo && state.grupo !== "resumo") q.set("grupo", state.grupo);
    if (state.modo === "media") q.set("modo", "media");
  }
  const qs = q.toString().replace(/%2F/gi, "/");
  history.replaceState(null, "", `/${tipo}/${id}${qs ? `?${qs}` : ""}`);
}

function bindEdit() {
  const e = state.data.entidade;
  document.querySelectorAll(".edit-pencil").forEach((btn) => {
    btn.addEventListener("click", () => {
      openEditModal({
        tipo: TIPO_EDIT[tipo],
        id: e.id,
        nome: e.nome,
        foto: e.foto,
        onSaved: async () => {
          await load();
          await render();
        },
      });
    });
  });
}

function tabelaJogador() {
  const linhas = state.data.linhas || [];
  return `
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr><th>Campeonato</th><th>Clube</th><th>J</th><th>Min</th><th>Gols</th><th>Ast</th><th>Nota</th></tr>
        </thead>
        <tbody>
          ${linhas
            .map(
              (r) => `<tr>
            <td><a class="camp-link" href="/liga/${r.campeonato_id}">${r.campeonato}</a></td>
            <td><a class="entity-link" href="/clube/${r.clube_id}">${r.clube}</a></td>
            <td>${r.jogos}</td><td>${r.minutos ?? "—"}</td>
            <td>${r.gols ?? 0}</td><td>${r.assistencias ?? 0}</td>
            <td>${n(r.rating, 2)}</td>
          </tr>`
            )
            .join("") || `<tr><td colspan="7">Sem dados.</td></tr>`}
        </tbody>
      </table>
    </div>`;
}

function digStat(chave, v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const k = String(chave || "");
  if (k === "gols" || k === "gols_marcados" || k === "gols_sofridos" || k === "gols_contra") {
    return n(Math.round(Number(v)), 0);
  }
  if (
    chave === "rating" ||
    chave === "precisao_chutes" ||
    chave === "xg" ||
    chave === "xa" ||
    chave === "xgot" ||
    chave === "xg_xa" ||
    chave === "xg_sem_penalti" ||
    chave === "xgot_sofrido" ||
    chave === "gols_evitados"
  ) {
    return n(v, 2);
  }
  return Number.isInteger(Number(v)) || Math.abs(Number(v) - Math.round(Number(v))) < 1e-9
    ? n(Math.round(Number(v)), 0)
    : n(v, 2);
}

function statsJogador() {
  const est = state.data.estatisticas || {};
  const grupos = est.grupos || {};
  const metricas = (est.metricas || {})[state.grupo] || [];
  const media = state.modo === "media";
  if (!Object.keys(grupos).length) {
    return `<div class="empty">Sem estatísticas nesta temporada.</div>`;
  }
  return `
    <div class="player-stats-head">
      <div class="tabs subtabs" id="jog-grupos" style="margin:0">
        ${Object.entries(grupos)
          .map(
            ([k, lab]) =>
              `<button type="button" class="tab ${state.grupo === k ? "active" : ""}" data-grupo="${k}">${lab}</button>`
          )
          .join("")}
      </div>
      <div class="filters-right" style="display:flex;align-items:center;gap:.75rem;flex-wrap:wrap">
        <span class="player-stats-meta">${est.jogos || 0} jogos · ${est.minutos || 0} min</span>
        <div class="modo-toggle">
          <button type="button" class="chip-btn ${media ? "on" : ""}" data-modo="media">Média</button>
          <button type="button" class="chip-btn ${!media ? "on" : ""}" data-modo="soma">Total</button>
        </div>
      </div>
    </div>
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr><th style="text-align:left">Métrica</th><th>${media ? "Média / jogo" : "Total"}</th></tr>
        </thead>
        <tbody>
          ${metricas
            .map((m) => {
              const v = media ? m.media : m.soma;
              const suf = m.chave === "precisao_chutes" && v != null ? "%" : "";
              return `<tr>
                <td style="text-align:left">${m.label}</td>
                <td><strong>${digStat(m.chave, v)}${suf}</strong></td>
              </tr>`;
            })
            .join("") || `<tr><td colspan="2">Sem dados neste grupo.</td></tr>`}
        </tbody>
      </table>
    </div>`;
}

function tabelaTecnico() {
  const linhas = rowsInScope();
  return `
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr><th>Campeonato</th><th>Clube</th><th>J</th><th>V</th><th>E</th><th>D</th><th>Pts</th></tr>
        </thead>
        <tbody>
          ${linhas
            .map(
              (r) => `<tr>
            <td><a class="camp-link" href="/liga/${r.campeonato_id}">${r.campeonato}</a></td>
            <td><a class="entity-link" href="/clube/${r.clube_id}">${r.clube}</a></td>
            <td>${r.jogos}</td><td>${r.v}</td><td>${r.e}</td><td>${r.d}</td><td><strong>${r.pts}</strong></td>
          </tr>`
            )
            .join("") || `<tr><td colspan="7">Sem dados.</td></tr>`}
        </tbody>
      </table>
    </div>`;
}

function tabelaArbitro() {
  const linhas = state.data.linhas || [];
  return `
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>Campeonato</th><th>Jogos</th><th>Gols</th></tr></thead>
        <tbody>
          ${linhas
            .map(
              (r) => `<tr>
            <td><a class="camp-link" href="/liga/${r.campeonato_id}">${r.campeonato}</a></td>
            <td>${r.jogos}</td><td>${r.gols ?? 0}</td>
          </tr>`
            )
            .join("") || `<tr><td colspan="3">Sem dados.</td></tr>`}
        </tbody>
      </table>
    </div>`;
}

/* Perfis: abas Geral/Estatísticas, filtros locais e análise de arbitragem. */
function rowsInScope() {
  const rows=state.data?.linhas||[];
  return rows.filter(r=>(!state.campeonatoFiltro||String(r.campeonato_id)===String(state.campeonatoFiltro))&&(!state.clubeFiltro||String(r.clube_id)===String(state.clubeFiltro)));
}
function filterProfileHtml(){
  if(tipo!=='tecnico')return '';
  const rows=state.data?.linhas||[];
  const leagues=[...new Map(rows.map(r=>[r.campeonato_id,r.campeonato])).entries()].filter(([id])=>id);
  const clubs=[...new Map(rows.map(r=>[r.clube_id,r.clube])).entries()].filter(([id])=>id);
  const opt=(pairs,selected,first)=>`<option value="">${first}</option>`+pairs.map(([id,label])=>`<option value="${id}" ${String(id)===String(selected)?'selected':''}>${label}</option>`).join('');
  return `<div class="df-person-profile-filters"><label>Campeonato<select id="df-profile-camp">${opt(leagues,state.campeonatoFiltro,'Todos')}</select></label><label>Clube<select id="df-profile-club">${opt(clubs,state.clubeFiltro,'Todos')}</select></label><span class="muted">Filtros aplicados à tabela. O radar considera todos os jogos sob comando do técnico na temporada.</span></div>`;
}
function coachStatsHtml(){
  const rows=rowsInScope();const games=rows.reduce((a,r)=>a+Number(r.jogos||0),0);
  const pts=rows.reduce((a,r)=>a+Number(r.pts||0),0);
  const wins=rows.reduce((a,r)=>a+Number(r.v||0),0);
  const draws=rows.reduce((a,r)=>a+Number(r.e||0),0);
  const losses=rows.reduce((a,r)=>a+Number(r.d||0),0);
  const metrics=[['Partidas',games],['Vitórias',wins],['Empates',draws],['Derrotas',losses],['Pontos',pts],['Aproveitamento',games?((100*pts)/(3*games)).toLocaleString('pt-BR',{maximumFractionDigits:1})+'%':'—']];
  return `<div class="df-ref-kpis">${metrics.map(([label,v])=>`<article class="df-ref-kpi"><span>${label}</span><strong>${v}</strong></article>`).join('')}</div>`;
}
function refereeTable(){
  const rows=state.data?.linhas||[];
  return `<div class="table-wrap"><table class="data-table"><thead><tr><th>Campeonato</th><th>J</th><th>Gols</th><th>Faltas</th><th>Amarelos</th><th>Vermelhos</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${r.campeonato_id?`<a href="/liga/${r.campeonato_id}">${r.campeonato}</a>`:r.campeonato}</td><td>${r.jogos??'—'}</td><td>${r.gols??'—'}</td><td>${r.faltas??'—'}</td><td>${r.amarelos??'—'}</td><td>${r.vermelhos??'—'}</td></tr>`).join('')||'<tr><td colspan="6">Resumo por campeonato indisponível; use a análise por partidas abaixo.</td></tr>'}</tbody></table></div>`;
}
function refereeAdvancedHtml(){return `<section class="section" id="df-ref-advanced"><h2 class="section-title">Análise por mando de campo</h2><p class="muted">Os índices são calculados exclusivamente sobre partidas confirmadas para este árbitro. O levantamento pode ser limitado pelo volume das APIs existentes.</p><button type="button" class="chip-btn" id="df-ref-analyze">Consultar partidas e estatísticas</button><div id="df-ref-result" aria-live="polite"></div></section>`;}
async function analyzeReferee(){
  const btn=$('#df-ref-analyze'),target=$('#df-ref-result');if(!btn||!target)return;
  btn.disabled=true;target.innerHTML='<p class="muted">Localizando campeonatos e partidas…</p>';
  try {
    const leagueR=await fetch('/api/ligas');if(!leagueR.ok)throw Error('Não foi possível consultar as ligas');
    const leagues=(await leagueR.json()).ligas||[];
    const selected=state.temporada;
    let leagueIds=(state.data.linhas||[]).map(r=>Number(r.campeonato_id)).filter(Boolean);
    if(!leagueIds.length){
      // Descoberta via ranking agregado de árbitros por liga, sem criar rotas no backend.
      const scan=leagues.slice(0,35),ids=[];let ptr=0;
      await Promise.all(Array.from({length:Math.min(5,scan.length)},async()=>{while(ptr<scan.length){const league=scan[ptr++];const response=await fetch(`/api/stats/arbitros?campeonato_id=${league.id}`);if(!response.ok)continue;const data=await response.json();if((data.itens||[]).some(a=>Number(a.id)===id))ids.push(Number(league.id));}}));
      leagueIds=ids;
    }
    const unique=[...new Set(leagueIds)].slice(0,12);
    if(!unique.length){target.innerHTML='<p class="muted">Nenhuma competição encontrada nas consultas disponíveis.</p>';return;}
    const candidates=[];
    for(const leagueId of unique){
      const q=selected?`?temporada=${encodeURIComponent(selected)}`:'';
      const response=await fetch(`/api/liga/${leagueId}${q}`);if(!response.ok)continue;
      const data=await response.json();for(const round of data.rodadas||[])for(const game of round.jogos||[])if(game.gols_casa!=null)candidates.push({id:game.id,campeonato:data.nome||`Liga ${leagueId}`});
    }
    const pool=[...new Map(candidates.map(g=>[g.id,g])).values()].slice(0,240);
    let ptr=0,complete=0,errors=0;
    const actual=[];
    await Promise.all(Array.from({length:Math.min(6,pool.length)},async()=>{while(ptr<pool.length){const candidate=pool[ptr++];try{const response=await fetch(`/api/jogo/${candidate.id}`);if(!response.ok)throw Error('HTTP '+response.status);const game=await response.json();if(Number(game.arbitro_id)===id)actual.push({...game,_league:candidate.campeonato});}catch(e){errors++;}complete++;if(complete%10===0)target.innerHTML=`<p class="muted">Consultadas ${complete}/${pool.length} partidas, ${actual.length} deste árbitro…</p>`;}}));
    if(!actual.length){target.innerHTML=`<p class="muted">Nenhuma partida identificada para este árbitro na amostra de ${pool.length} jogos. Não é possível estimar os indicadores por mando.</p>`;return;}
    const games=actual.length;const totals={homeWins:0,homeNonLoss:0,awayWins:0,draws:0,offsideHome:0,offsideAway:0,foulsHome:0,foulsAway:0,yellowsHome:0,yellowsAway:0,redsHome:0,redsAway:0};
    const sum=(k)=>actual.reduce((acc,g)=>acc+(Number(g.estatisticas?.completo?.Casa?.[k])||0)+(Number(g.estatisticas?.completo?.Fora?.[k])||0),0);
    for(const g of actual){
      const home=Number(g.gols_casa),away=Number(g.gols_fora);
      if(home>away)totals.homeWins++;if(home>=away)totals.homeNonLoss++;if(away>home)totals.awayWins++;if(home===away)totals.draws++;
      const h=g.estatisticas?.completo?.Casa||{},a=g.estatisticas?.completo?.Fora||{};
      totals.offsideHome+=Number(h.impedimentos)||0;totals.offsideAway+=Number(a.impedimentos)||0;
      totals.foulsHome+=Number(h.faltas_cometidas)||0;totals.foulsAway+=Number(a.faltas_cometidas)||0;
      totals.yellowsHome+=Number(h.cartao_amarelo)||0;totals.yellowsAway+=Number(a.cartao_amarelo)||0;
      totals.redsHome+=Number(h.cartao_vermelho)||0;totals.redsAway+=Number(a.cartao_vermelho)||0;
    }
    const percent=x=>(100*x/games).toLocaleString('pt-BR',{maximumFractionDigits:1})+'%';
    const byLeague=new Map();for(const g of actual){const l=byLeague.get(g._league)||{games:0,yellows:0,reds:0,fouls:0};l.games++;for(const side of ['Casa','Fora']){const e=g.estatisticas?.completo?.[side]||{};l.yellows+=Number(e.cartao_amarelo)||0;l.reds+=Number(e.cartao_vermelho)||0;l.fouls+=Number(e.faltas_cometidas)||0;}byLeague.set(g._league,l);}
    const items=[['Vitórias do mandante',percent(totals.homeWins)],['Mandante vence ou empata',percent(totals.homeNonLoss)],['Vitórias do visitante',percent(totals.awayWins)],['Empates',percent(totals.draws)],['Impedimentos — mandante',totals.offsideHome],['Impedimentos — visitante',totals.offsideAway],['Faltas cometidas — mandante',totals.foulsHome],['Faltas cometidas — visitante',totals.foulsAway],['Faltas a favor do mandante',totals.foulsAway],['Faltas a favor do visitante',totals.foulsHome],['Amarelos — mandante',totals.yellowsHome],['Amarelos — visitante',totals.yellowsAway],['Vermelhos — mandante',totals.redsHome],['Vermelhos — visitante',totals.redsAway],['Gols anulados','Não disponível']];
    target.innerHTML=`<p class="muted">Amostra: <strong>${games} partidas confirmadas</strong> entre ${pool.length} consultadas. ${errors?`${errors} consultas falharam.`:''} Os percentuais se referem apenas a essa amostra e não representam necessariamente toda a carreira.</p><div class="df-ref-kpis">${items.map(([k,v])=>`<article class="df-ref-kpi"><span>${k}</span><strong>${v}</strong></article>`).join('')}</div><h3>Partidas confirmadas por campeonato</h3><div class="table-wrap"><table class="data-table"><thead><tr><th>Campeonato</th><th>J</th><th>Faltas</th><th>Amarelos</th><th>Vermelhos</th></tr></thead><tbody>${[...byLeague].map(([name,r])=>`<tr><td>${name}</td><td>${r.games}</td><td>${r.fouls}</td><td>${r.yellows}</td><td>${r.reds}</td></tr>`).join('')}</tbody></table></div>`;
  }catch(e){target.innerHTML=`<p class="error">Falha na análise: ${String(e.message||e)}</p>`;}finally{btn.disabled=false;}
}
async function render(){
 const e=state.data.entidade||{};
 const title=tipo==='jogador'?'Jogador':tipo==='tecnico'?'Técnico':'Árbitro';
 document.title=e.nome||title;
 const tabs=tipo==='arbitro'?[['geral','Geral'],['estatisticas','Estatísticas']]:[['geral','Geral'],['estatisticas','Estatísticas']];
 if(!tabs.some(([k])=>k===state.aba))state.aba='geral';
 const header=`<div class="entity-header"><div class="entity-photo-wrap">${img(e.foto,'entity-photo')}${pencilBtn('on-photo')}</div><div><div class="entity-name-row"><h1 class="page-title entity-title">${e.nome||title}</h1>${pencilBtn('on-name')}</div><p class="muted">${e.posicao||''}${e.nacionalidade?` · ${e.nacionalidade}`:''}${e.pais?` · ${e.pais}`:''}</p></div><label class="entity-temp season-select">Temporada<select id="ent-temp">${(state.data.temporadas||[]).map(t=>`<option value="${t}" ${t===state.temporada?'selected':''}>${t}</option>`).join('')}${!(state.data.temporadas||[]).length?'<option value="">Todas as disponíveis</option>':''}</select></label></div>`;
 const bar=`<div class="tabs" id="df-entity-tabs">${tabs.map(([key,label])=>`<button type="button" class="tab ${state.aba===key?'active':''}" data-entity-tab="${key}">${label}</button>`).join('')}</div>`;
 let content='';
 if(tipo==='jogador'){
  content=state.aba==='geral'?`<section class="section"><h2 class="section-title">Desempenho na temporada</h2>${tabelaJogador()}</section><div id="df-profile-radar-slot"></div>`:`<section class="section"><h2 class="section-title">Estatísticas por categoria</h2>${statsJogador()}</section>`;
 }else if(tipo==='tecnico'){
  content=filterProfileHtml()+(state.aba==='geral'?`<section class="section"><h2 class="section-title">Temporada por campeonato e clube</h2>${tabelaTecnico()}</section><div id="df-profile-radar-slot"></div>`:`<section class="section"><h2 class="section-title">Indicadores de desempenho</h2>${coachStatsHtml()}</section>`);
 }else{
  content=state.aba==='geral'?`<section class="section"><h2 class="section-title">Jogos por campeonato</h2>${refereeTable()}</section>`:`${refereeAdvancedHtml()}`;
 }
 $('#conteudo').innerHTML=header+bar+content;
 setFavicon(e.foto);bindEdit();syncUrl();
 $('#ent-temp')?.addEventListener('change',async ev=>{state.temporada=ev.target.value||null;await load();await render();});
 $('#df-entity-tabs')?.addEventListener('click',ev=>{const btn=ev.target.closest('[data-entity-tab]');if(!btn)return;state.aba=btn.dataset.entityTab;render();});
 $('#df-profile-camp')?.addEventListener('change',ev=>{state.campeonatoFiltro=ev.target.value||'';render();});
 $('#df-profile-club')?.addEventListener('change',ev=>{state.clubeFiltro=ev.target.value||'';render();});
 if(tipo==='jogador'&&state.aba==='estatisticas'){
  $('#jog-grupos')?.addEventListener('click',ev=>{const btn=ev.target.closest('[data-grupo]');if(!btn)return;state.grupo=btn.dataset.grupo;syncUrl();render();});
  document.querySelectorAll('[data-modo]').forEach(btn=>btn.addEventListener('click',()=>{state.modo=btn.dataset.modo;syncUrl();render();}));
 }
 if(tipo==='arbitro'&&state.aba==='estatisticas')$('#df-ref-analyze')?.addEventListener('click',analyzeReferee);
}

async function init() {
  const navKey =
    tipo === "jogador" ? "jogadores" : tipo === "tecnico" ? "tecnicos" : tipo === "arbitro" ? "arbitros" : "";
  const navEl = document.querySelector("[data-nav]");
  if (navEl) navEl.dataset.nav = navKey;
  initNav(navKey);
  try {
    await load();
    await render();
  } catch (e) {
    setSiteFavicon();
    $("#conteudo").innerHTML = `<div class="error">${e.message}</div>`;
  }
}

init();
