import "./shot-visuals.js?v=player-visuals-v1-20261106";
// Dados do jogador: mapas partilhados com os detalhes de partida.

const escapeHTML=x=>String(x??"").replace(/[&<>"']/g,c=>({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
}[c]));
const integer=x=>Number(x||0).toLocaleString("pt-BR");
const percent=x=>Number(x||0).toLocaleString("pt-BR",{
  minimumFractionDigits:1,maximumFractionDigits:1
})+"%";
const decimal=x=>x==null?"—":Number(x).toLocaleString("pt-BR",{
  minimumFractionDigits:2,maximumFractionDigits:2
});
const cache=new Map();
const color=x=>x.gol?"goal":x.defesa?"saved":"miss";
const displayed=(r,f)=>f==="todos"||(
  f==="gol"?r.gol:f==="defesa"?r.defesa:f==="alvo"?r.no_alvo:!r.no_alvo
);
function card(title,ratio,done,total,note){
  return `<article class="player-shot-card"><h3>${escapeHTML(title)}</h3>
    <strong class="player-shot-percent">${percent(ratio)}</strong>
    <div class="player-shot-progress"><span style="width:${Math.min(100,Math.max(0,Number(ratio)||0))}%"></span></div>
    <footer><strong>${integer(done)} / ${integer(total)}</strong><span>${escapeHTML(note)}</span></footer>
  </article>`;
}
function kpi(label,value,note){
  return `<article class="player-shot-summary-card"><span>${escapeHTML(label)}</span>
    <strong>${escapeHTML(value)}</strong><small>${escapeHTML(note)}</small></article>`;
}
function labels(gk,filter,view){
  const entries=gk?[
    ["todos","Todas"],["defesa","Defendidas"],["gol","Gols sofridos"],["outros","Outras"]
  ]:[
    ["todos","Todas"],["gol","Gols"],["alvo","No alvo"],["outros","Outras"]
  ];
  return `<div class="player-shot-filters" role="group" aria-label="Filtrar finalizações">`+
    entries.map(([key,name])=>
      `<button type="button" class="tab ${key===filter?"active":""}"
        data-shot-filter="${key}" data-shot-view="${view}" aria-pressed="${key===filter}">
        ${name}</button>`).join("")+"</div>";
}
function selectedCard(shot,gk){
  if(!shot)return `<div class="player-shot-selected-empty">Selecione um ponto para consultar o lance.</div>`;
  const minute=shot.minuto==null?"—":`${integer(shot.minuto)}${shot.minuto_adicional?"+"+integer(shot.minuto_adicional):""}'`;
  return `<div class="player-shot-selected">
    <p><span class="player-shot-result ${color(shot)}">${escapeHTML(shot.tipo_evento||"Finalização")}</span>
      <strong>${escapeHTML(gk?shot.atacante||"Adversário":shot.tipo_finalizacao||"Finalização")}</strong></p>
    <p>${minute} · ${escapeHTML(shot.campeonato||"Campeonato")} · ${escapeHTML(String(shot.data||"").slice(0,10))}</p>
    <p>${escapeHTML(shot.situacao_jogada||"Jogada")} · xG: ${decimal(shot.xg)} · xGOT: ${decimal(shot.xgot)}</p>
    <a href="/jogo/${Number(shot.jogo_id)}">Ver partida</a></div>`;
}
function dot(shot,view,goal){
  const position=goal?window.DFShotMap.goalPosition(shot):window.DFShotMap.shotPos(shot);
  if(!position||(goal&&!position.visible))return "";
  const left=goal?100*position.x/560:position.left;
  const top=goal?100*position.y/275:position.top;
  return `<button type="button" class="${goal?"player-goal-dot":"player-shot-dot"} ${color(shot)}"
    style="left:${left.toFixed(3)}%;top:${top.toFixed(3)}%"
    data-select-shot="${shot.id}" data-shot-view="${view}"
    title="${escapeHTML(shot.tipo_evento)} · ${escapeHTML(shot.minuto)}'"
    aria-label="Selecionar finalização ${escapeHTML(shot.tipo_evento)}"></button>`;
}
function maps(title,all,gk,view,filter,id,description){
  const rows=all.filter(x=>displayed(x,filter));
  const current=rows.find(x=>String(x.id)===String(id))||rows[0]||null;
  const pitchDots=rows.map(s=>dot(s,view,false)).join("");
  const goalDots=rows.map(s=>dot(s,view,true)).join("");
  return `<section class="section player-shot-map-section">
    <h2 class="section-title">${escapeHTML(title)}</h2>
    <p class="player-shot-help">${escapeHTML(description)}</p>
    ${labels(gk,filter,view)}
    <div class="player-shot-map-grid">
      <div class="player-shot-field-panel">
        <h3>Origem da finalização</h3>
        <div class="player-shot-field">${window.DFShotMap.pitchSvg()}${pitchDots}</div>
        <p class="player-shot-help">${integer(rows.length)} finalizações no filtro.</p>
      </div>
      <div class="player-shot-goal-column">
        <div class="player-shot-goal-panel">
          <h3>Destino da bola — gol de frente</h3>
          <div class="player-shot-goal">${window.DFShotMap.goalSvg(null)}${goalDots}</div>
          <p class="player-shot-help">Os pontos mostram a trajetória final registrada, não a movimentação do goleiro.</p>
        </div>
        ${selectedCard(current,gk)}
        <div class="player-shot-legend">
          <span><i class="goal"></i>${gk?"Gol sofrido":"Gol"}</span>
          <span><i class="saved"></i>${gk?"Defesa":"Chute defendido"}</span>
          <span><i class="miss"></i>Outros</span>
        </div>
      </div>
    </div>
  </section>`;
}
function group(title,groupData,p,gk){
  return `<h3 class="player-shot-subheading">${escapeHTML(title)}</h3>
    <div class="player-shot-cards">${groupData.map(r=>
      `<article class="player-shot-card"><h3>${escapeHTML(r.label)}</h3>
        <strong class="player-shot-percent">${percent(r.distribuicao_pct)}</strong>
        <div class="player-shot-progress"><span style="width:${r.distribuicao_pct}%"></span></div>
        <footer><strong>${integer(r.tentativas)} / ${integer(p.tentativas)}</strong><span>cobranças nessa região</span></footer>
        <p class="player-shot-submetric">${gk?"Defesas":"Gols"}:
          ${integer(gk?r.defesas:r.gols)} (${percent(r.tentativas?100*(gk?r.defesas:r.gols)/r.tentativas:0)})</p>
      </article>`).join("")}</div>`;
}
function penalties(p,gk){
  return `<section class="section player-shot-penalty-section">
    <h2 class="section-title">${gk?"Pênaltis enfrentados":"Pênaltis cobrados"}</h2>
    <p class="player-shot-help">Todos os percentuais consideram as cobranças registradas.
      O destino da bola é apresentado pela perspectiva de quem olha o gol de frente.</p>
    <div class="player-shot-cards">
      ${card(gk?"Pênaltis defendidos":"Conversão de pênaltis",
        p.acerto_pct,p.acertos,p.tentativas,gk?"defesas / cobranças":"gols / cobranças")}
      ${kpi(gk?"Gols sofridos":"Gols marcados",integer(p.gols),"em pênaltis")}
      ${kpi(gk?"Defesas":"Chutes no alvo",integer(gk?p.defesas:p.no_alvo),
        "nas cobranças")}
    </div>
    ${group("Esquerda, centro e direita",p.lados,p,gk)}
    ${group("Altura da bola no gol",p.alturas,p,gk)}
    <p class="player-shot-help">As faixas são estimadas pela altura da bola ao cruzar a linha do gol:
      rasteiro até 0,60 m, meia-altura até 1,50 m, alto acima de 1,50 m.
      Isso não revela o gesto técnico do chute ou a direção do salto do goleiro.</p>
  </section>`;
}
function renderContent(data,filters,chosen,mode){
  const gk=data.tipo==="goleiro",r=data.resumo||{};
  if(mode==="penaltis"){
    if(!data.penaltis)return '<section class="section"><p>Não há cobranças registradas nesta temporada.</p></section>';
    return penalties(data.penaltis,gk)+
      maps(gk?"Mapa dos pênaltis contra o goleiro":"Mapa das cobranças de pênalti",
        data.penaltis.mapa||[],gk,"penaltis",filters.penaltis,chosen.penaltis,
        "Selecione uma cobrança para ver seus detalhes e o destino da bola no gol.")+
      (gk?`<section class="section player-shot-dive-note">
        <h2 class="section-title">Lado do mergulho do goleiro</h2>
        <p>O banco registra onde a bola foi, mas não registra para qual lado o goleiro saltou.
          Por isso, não é possível apresentar um mapa fiel dos movimentos do goleiro.</p>
      </section>`:"");
  }
  const headline=gk?[
    ["Defesas",integer(r.defesas),"finalizações defendidas"],
    ["Chutes no alvo",integer(r.no_alvo),"goleiro identificado"],
    ["Gols sofridos",integer(r.gols),"nesses chutes"],
    ["Taxa de defesas",percent(r.acerto_pct),"defesas / chutes no alvo"]
  ]:[
    ["Tentativas",integer(r.tentativas),"finalizações"],
    ["No alvo",integer(r.no_alvo),"gols e defendidas"],
    ["Gols",integer(r.gols),"marcados"],
    ["Precisão",percent(r.acerto_pct),"no alvo / tentativas"]
  ];
  let out=`<section class="section player-shot-overview">
    <h2 class="section-title">${gk?"Desempenho das defesas":"Desempenho das finalizações"}</h2>
    <div class="player-shot-summary">${headline.map(x=>kpi(...x)).join("")}</div>
    <p class="player-shot-help">${escapeHTML(data.cobertura)} Os totais consideram todas as finalizações
      disponíveis na temporada; os mapas exibem até as 900 mais recentes.</p>
    <h3 class="player-shot-subheading">${gk?"Defesas por tipo de chute recebido":"Acerto por tipo de finalização"}</h3>
    <div class="player-shot-cards">${(data.tipos||[]).map(x=>card(
      x.label,x.acerto_pct,x.acertos,gk?x.no_alvo:x.tentativas,
      gk?"defesas / chutes no alvo":"acertos / tentativas")).join("")}</div>
  </section>`;
  out+=maps(gk?"Mapa das finalizações adversárias":"Mapa das finalizações",
    data.mapa||[],gk,"principal",filters.principal,chosen.principal,
    gk?"Chutes com goleiro identificado, resultados e posições da bola.":
       "Mapa de chutes e gol frontal compartilhado com as páginas de partida.");
  if(!r.tentativas)out+=`<p class="player-shot-help">Nenhuma finalização identificada na temporada selecionada.</p>`;
  return out;
}
export async function mountPlayerShots(root,playerId,season,mode="principal"){
  if(!root)return;
  const key=String(playerId)+"|"+String(season||"");
  root.dataset.shotsKey=key+"|"+mode;
  root.innerHTML='<section class="section"><p class="player-shot-help">Carregando dados das finalizações…</p></section>';
  try{
    if(!cache.has(key)){
      const params=new URLSearchParams();
      if(season)params.set("temporada",season);
      const url="/api/jogador/"+encodeURIComponent(playerId)+"/finalizacoes?"+params;
      cache.set(key,fetch(url).then(async response=>{
        if(!response.ok)throw Error("Falha ao consultar finalizações (HTTP "+response.status+").");
        return response.json();
      }).catch(error=>{cache.delete(key);throw error;}));
    }
    const data=await cache.get(key);
    if(!root.isConnected||root.dataset.shotsKey!==key+"|"+mode)return;
    const filters={principal:"todos",penaltis:"todos"};
    const chosen={principal:null,penaltis:null};
    const show=()=>{root.innerHTML=renderContent(data,filters,chosen,mode);};
    root.addEventListener("click",event=>{
      const filter=event.target.closest("[data-shot-filter]");
      if(filter){
        const view=filter.dataset.shotView;
        if(!Object.prototype.hasOwnProperty.call(filters,view))return;
        filters[view]=filter.dataset.shotFilter;
        chosen[view]=null;
        show();
        return;
      }
      const shot=event.target.closest("[data-select-shot]");
      if(!shot)return;
      const view=shot.dataset.shotView;
      if(!Object.prototype.hasOwnProperty.call(chosen,view))return;
      chosen[view]=shot.dataset.selectShot;
      show();
    });
    show();
  }catch(error){
    if(root.isConnected&&root.dataset.shotsKey===key+"|"+mode)
      root.innerHTML='<section class="section"><p class="error">'+escapeHTML(error.message)+'</p></section>';
  }
}
