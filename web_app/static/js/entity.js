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
  return `<div class="df-person-profile-filters"><label>Campeonato<select id="df-profile-camp">${opt(leagues,state.campeonatoFiltro,'Todos')}</select></label><label>Clube<select id="df-profile-club">${opt(clubs,state.clubeFiltro,'Todos')}</select></label><span class="muted">Filtros aplicados à tabela e ao radar do técnico.</span></div>`;
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

const safeText = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const displayNum = (v, d=0) => v==null ? '—' : Number(v).toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d});
const displayPct = v=>v==null?'—':displayNum(v,1)+'%';

function refereeTable(){
  const rows=state.data?.linhas||[];
  return '<div class="table-wrap"><table class="data-table"><thead><tr><th>Campeonato</th><th>Jogos</th><th>Faltas</th><th>Amarelos</th><th>Vermelhos</th><th>% mandante</th><th>% visitante</th></tr></thead><tbody>'+
    (rows.map(r=>'<tr><td><a href="/liga/'+r.campeonato_id+'">'+safeText(r.campeonato)+'</a></td><td>'+displayNum(r.jogos)+'</td><td>'+displayNum(r.faltas)+'</td><td>'+displayNum(r.amarelos)+'</td><td>'+displayNum(r.vermelhos)+'</td><td>'+displayPct(r.pct_mandante)+'</td><td>'+displayPct(r.pct_visitante)+'</td></tr>').join('')||
    '<tr><td colspan="7">Sem partidas disponíveis no período selecionado.</td></tr>')+
    '</tbody></table></div>';
}
function refereeCards(){
  const r=state.data?.resumo||{};
  const metrics=[
    ['Partidas apitadas',displayNum(r.jogos)],['Vitórias do mandante',displayPct(r.pct_mandante)],
    ['Mandante venceu ou empatou',displayPct(r.pct_mandante_ou_empate)],['Vitórias do visitante',displayPct(r.pct_visitante)],
    ['Empates',displayPct(r.pct_empates)],['Faltas marcadas',displayNum(r.faltas)],
    ['Faltas cometidas — mandante',displayNum(r.faltas_casa)],['Faltas cometidas — visitante',displayNum(r.faltas_fora)],
    ['Faltas a favor do mandante',displayNum(r.faltas_fora)],['Faltas a favor do visitante',displayNum(r.faltas_casa)],
    ['Amarelos mandante',displayNum(r.amarelos_casa)],['Amarelos visitante',displayNum(r.amarelos_fora)],
    ['Vermelhos mandante',displayNum(r.vermelhos_casa)],['Vermelhos visitante',displayNum(r.vermelhos_fora)],
    ['Impedimentos mandante',displayNum(r.impedimentos_casa)],['Impedimentos visitante',displayNum(r.impedimentos_fora)],
    ['Gols anulados','Sem dados'],
  ];
  return '<div class="df-ref-kpis">'+metrics.map(([name,value])=>'<article class="df-ref-kpi"><span>'+name+'</span><strong>'+value+'</strong></article>').join('')+'</div>';
}
function refereeRadar(){
  const r=state.data?.resumo||{},games=Number(r.jogos||0);
  const per=(key,max)=>games>0&&r[key]!=null?Math.max(0,Math.min(100,100*Number(r[key])/games/max)):null;
  const labels=['Vitórias mandante','Vitórias visitante','Faltas/jogo','Cartões mandante','Cartões visitante'];
  const values=[r.pct_mandante,r.pct_visitante,per('faltas',35),per('amarelos_casa',4),per('amarelos_fora',4)]
    .map(v=>v==null||!Number.isFinite(Number(v))?null:Math.max(0,Math.min(100,Number(v))));
  const p=(i,f)=>{const a=-Math.PI/2+2*Math.PI*i/5;return [200+135*f*Math.cos(a),190+135*f*Math.sin(a)];};
  const pts=(f)=>labels.map((_,i)=>p(i,f).join(',')).join(' ');
  const grid=[.25,.5,.75,1].map(f=>'<polygon points="'+pts(f)+'" fill="none" stroke="var(--radar-grid,#424957)"/>').join('');
  const lines=labels.map((_,i)=>'<line x1="200" y1="190" x2="'+p(i,1).join('" y2="')+'" stroke="var(--radar-grid,#424957)"/>').join('');
  const poly=values.every(v=>v!=null)?'<polygon points="'+labels.map((_,i)=>p(i,values[i]/100).join(',')).join(' ')+'" fill="var(--radar-fill,rgba(255,107,26,.19))" stroke="var(--accent,#ff6b1a)" stroke-width="3"/>':'';
  const dots=values.map((v,i)=>v==null?'':'<circle cx="'+p(i,v/100)[0]+'" cy="'+p(i,v/100)[1]+'" r="4" fill="var(--accent,#ff6b1a)"/>').join('');
  const annotation=labels.map((label,i)=>{const xy=p(i,1.23);return '<text x="'+xy[0]+'" y="'+xy[1]+'" text-anchor="middle" fill="var(--text,#fff)" font-size="11">'+safeText(label)+'</text>'}).join('');
  return '<section class="section"><h2 class="section-title">Perfil de arbitragem</h2><p class="muted">Índice visual de 0 a 100. Vitórias são percentuais observados; faltas e cartões são normalizados por partida, não indicam qualidade do árbitro.</p><div class="df-ref-radar-layout"><svg viewBox="0 0 400 400" role="img" aria-label="Radar estatístico do árbitro">'+grid+lines+poly+dots+annotation+'</svg><div class="df-ref-radar-list">'+labels.map((name,i)=>'<div><span>'+name+'</span><strong>'+(values[i]==null?'—':Math.round(values[i])+'/100')+'</strong></div>').join('')+'</div></div></section>';
}
function refereeGames(){
  const rows=state.data?.jogos||[];
  return '<section class="section"><h2 class="section-title">Jogos apitados · '+rows.length+'</h2><div class="table-wrap"><table class="data-table"><thead><tr><th>Data</th><th>Campeonato</th><th>Mandante</th><th>Placar</th><th>Visitante</th><th>Faltas</th><th>Amarelos</th><th>Vermelhos</th></tr></thead><tbody>'+
    (rows.map(g=>{const sum=(a,b)=>g[a]!=null&&g[b]!=null?Number(g[a])+Number(g[b]):null;return '<tr><td>'+safeText(String(g.data||'').slice(0,10))+'</td><td>'+safeText(g.campeonato)+'</td><td>'+safeText(g.casa)+'</td><td><a href="/jogo/'+g.id+'">'+displayNum(g.gols_casa)+' × '+displayNum(g.gols_fora)+'</a></td><td>'+safeText(g.fora)+'</td><td>'+displayNum(sum('faltas_casa','faltas_fora'))+'</td><td>'+displayNum(sum('amarelos_casa','amarelos_fora'))+'</td><td>'+displayNum(sum('vermelhos_casa','vermelhos_fora'))+'</td></tr>'}).join('')||
    '<tr><td colspan="8">Sem jogos registrados.</td></tr>')+
    '</tbody></table></div></section>';
}
async function render(){
 const e=state.data.entidade||{};
 const title=tipo==='jogador'?'Jogador':tipo==='tecnico'?'Técnico':'Árbitro';
 document.title=e.nome||title;
 const tabs=tipo==='arbitro'?[['geral','Geral'],['estatisticas','Estatísticas'],['jogos','Jogos']]:[['geral','Geral'],['estatisticas','Estatísticas']];
 if(!tabs.some(([k])=>k===state.aba))state.aba='geral';
 const header=`<div class="entity-header"><div class="entity-photo-wrap">${img(e.foto,'entity-photo')}${pencilBtn('on-photo')}</div><div><div class="entity-name-row"><h1 class="page-title entity-title">${e.nome||title}</h1>${pencilBtn('on-name')}</div><p class="muted">${e.posicao||''}${e.nacionalidade?` · ${e.nacionalidade}`:''}${e.pais?` · ${e.pais}`:''}</p></div><label class="entity-temp season-select">Temporada<select id="ent-temp">${(state.data.temporadas||[]).map(t=>`<option value="${t}" ${t===state.temporada?'selected':''}>${t}</option>`).join('')}${!(state.data.temporadas||[]).length?'<option value="">Todas as disponíveis</option>':''}</select></label></div>`;
 const bar=`<div class="tabs" id="df-entity-tabs">${tabs.map(([key,label])=>`<button type="button" class="tab ${state.aba===key?'active':''}" data-entity-tab="${key}">${label}</button>`).join('')}</div>`;
 let content='';
 if(tipo==='jogador'){
  content=state.aba==='geral'?`<section class="section"><h2 class="section-title">Desempenho na temporada</h2>${tabelaJogador()}</section><div id="df-profile-radar-slot"></div>`:`<section class="section"><h2 class="section-title">Estatísticas por categoria</h2>${statsJogador()}</section>`;
 }else if(tipo==='tecnico'){
  content=filterProfileHtml()+(state.aba==='geral'?`<section class="section"><h2 class="section-title">Temporada por campeonato e clube</h2>${tabelaTecnico()}</section><div id="df-profile-radar-slot"></div>`:`<section class="section"><h2 class="section-title">Indicadores de desempenho</h2>${coachStatsHtml()}</section>`);
 }else{
  content=state.aba==='geral'?`<section class="section"><h2 class="section-title">Temporada por campeonato</h2>${refereeTable()}</section>${refereeRadar()}`:state.aba==='estatisticas'?`<section class="section"><h2 class="section-title">Análise por mando de campo</h2>${refereeCards()}</section>`:refereeGames();
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
