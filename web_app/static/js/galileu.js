/* Galileu — validação prospectiva de estratégias Nostradamus. */
(()=>{
"use strict";
const $=s=>document.querySelector(s);
const escapeHTML=v=>String(v??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const numeric=v=>v==null||!Number.isFinite(Number(v))?"—":Number(v).toLocaleString("pt-BR",{maximumFractionDigits:2});
const DAY=864e5;
const tomorrow=new Date();tomorrow.setDate(tomorrow.getDate()+1);
const iso=d=>[d.getFullYear(),String(d.getMonth()+1).padStart(2,"0"),String(d.getDate()).padStart(2,"0")].join("-");
$("#gl-date").min=iso(tomorrow);$("#gl-date").value=iso(tomorrow);
let strategies=[],games=[];
const status=(message,error=false)=>{$("#gl-notice").innerHTML='<p class="gl-alert '+(error?"gl-error":"")+'">'+escapeHTML(message)+'</p>';};
function loadMethods(){
  try {
    const data=JSON.parse(localStorage.getItem("df_nostradamus_estrategias_v1")||"[]");
    return Array.isArray(data)?data.filter(s=>s&&typeof s.nome==="string"&&s.nome.trim()&&Array.isArray(s.condicoes)).slice(0,50):[];
  }catch(e){status("Não foi possível ler os métodos salvos: "+e.message,true);return [];}
}
const json=async (url,options)=>{
  const response=await fetch(url,options);
  const body=await response.json();
  if(!response.ok)throw Error(typeof body.detail==="string"?body.detail:"Erro ao acessar o servidor.");
  return body;
};
const post=(url,obj)=>json(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(obj)});
function badge(status){
  const txt=status==="green"?"Green":status==="red"?"Red":"Pendente";
  return '<span class="gl-status gl-'+escapeHTML(status)+'">'+txt+'</span>';
}
function renderBank(data){
  $("#gl-balance").textContent=numeric(data.banca_atual)+" u";
  $("#gl-entries").textContent=numeric(data.resumo.entradas);
  $("#gl-pending").textContent=numeric(data.resumo.pendentes);
}
async function refreshBank(){
  try{renderBank(await json("/api/apostas/galileu/relatorio"));}
  catch(e){status(e.message,true);}
}
const percent=metric=>metric==null?"—":numeric(metric);
function renderStats(game){
  const entries=[
    ["Partidas usadas",game.amostra.mandante,game.amostra.visitante],
    ["Pontos por jogo",game.estatisticas.mandante.pontos_jogo,game.estatisticas.visitante.pontos_jogo],
    ["Aproveitamento (%)",game.estatisticas.mandante.aproveitamento,game.estatisticas.visitante.aproveitamento],
    ["Gols por jogo",game.estatisticas.mandante.gols_feitos,game.estatisticas.visitante.gols_feitos],
    ["Gols sofridos por jogo",game.estatisticas.mandante.gols_sofridos,game.estatisticas.visitante.gols_sofridos],
    ["Saldo médio",game.estatisticas.mandante.saldo,game.estatisticas.visitante.saldo],
    ["xG",game.estatisticas.mandante.xg,game.estatisticas.visitante.xg],
    ["xGOT",game.estatisticas.mandante.xgot,game.estatisticas.visitante.xgot],
    ["Finalizações",game.estatisticas.mandante.chutes,game.estatisticas.visitante.chutes],
    ["Finalizações certas",game.estatisticas.mandante.chutes_certos,game.estatisticas.visitante.chutes_certos],
    ["Passes certos",game.estatisticas.mandante.passes_certos,game.estatisticas.visitante.passes_certos],
    ["Passes certos por gol",game.estatisticas.mandante.passes_por_gol,game.estatisticas.visitante.passes_por_gol],
    ["Finalizações por gol",game.estatisticas.mandante.chutes_por_gol,game.estatisticas.visitante.chutes_por_gol],
    ["Eficiência xG (%)",game.estatisticas.mandante.xg_conversao,game.estatisticas.visitante.xg_conversao],
    ["Posse de bola (%)",game.estatisticas.mandante.posse,game.estatisticas.visitante.posse],
    ["Grandes chances",game.estatisticas.mandante.grandes_chances,game.estatisticas.visitante.grandes_chances],
    ["Escanteios",game.estatisticas.mandante.escanteios,game.estatisticas.visitante.escanteios],
    ["Dribles certos",game.estatisticas.mandante.dribles_certos,game.estatisticas.visitante.dribles_certos],
    ["Duelos aéreos",game.estatisticas.mandante.duelos_aereos,game.estatisticas.visitante.duelos_aereos],
  ];
  return '<div class="gl-scroll"><table class="gl-table gl-stat-table"><thead><tr><th>Indicador</th>'+
     '<th>'+escapeHTML(game.mandante)+'</th><th>'+escapeHTML(game.visitante)+'</th></tr></thead><tbody>'+
     entries.map(x=>'<tr><td>'+escapeHTML(x[0])+'</td><td>'+percent(x[1])+'</td><td>'+percent(x[2])+'</td></tr>').join("")+
     '</tbody></table></div><p class="gl-note">Médias históricas exclusivamente anteriores ao confronto, na mesma liga e temporada. Indicadores ausentes aparecem como —.</p>';
}
function renderRules(method){
  const all=method.regras||[];
  return '<div class="gl-rule-grid">'+all.map(r=>
    '<div><b>'+escapeHTML(r.lado==="visitante"?"Visitante":"Mandante")+' · '+escapeHTML(r.nome)+
    '</b> <span>'+numeric(r.observado)+' '+escapeHTML(r.comparador)+' '+numeric(r.comparado)+
    '</span></div>').join("")+'</div>';
}
function renderGame(g){
  const key=String(g.jogo_id);
  const methods=g.metodos.map(m=>'<option value="'+m.metodo_idx+'">'+escapeHTML(m.nome)+' — '+escapeHTML(m.objetivo_nome)+'</option>').join("");
  const initial=g.metodos[0];
  const marketOptions=Object.entries(knownMarkets()).map(([id,name])=>
    '<option value="'+escapeHTML(id)+'" '+(id===initial.objetivo?"selected":"")+'>'+escapeHTML(name)+'</option>').join("");
  return '<article class="gl-game" data-id="'+key+'">'+
   '<div class="gl-game-main"><label class="gl-checkbox"><input type="checkbox" class="gl-check" aria-label="Marcar '+escapeHTML(g.mandante)+' contra '+escapeHTML(g.visitante)+'"></label>'+
   '<div class="gl-game-body"><div class="gl-meta"><span>'+escapeHTML(g.data)+'</span><span>'+escapeHTML(g.campeonato)+'</span><span>'+escapeHTML(g.rodada||"Próxima rodada")+'</span></div>'+
   '<details class="gl-stat-detail"><summary class="gl-teams">'+escapeHTML(g.mandante)+' <span>×</span> '+escapeHTML(g.visitante)+'</summary>'+renderStats(g)+'</details>'+
   '<div class="gl-match-form"><label>Método compatível<select class="gl-method">'+methods+'</select></label>'+
   '<label>Entrada neste jogo<select class="gl-market">'+marketOptions+'</select></label></div>'+
   '<details class="gl-method-detail"><summary>Ver regras do método</summary><div class="gl-method-rules">'+renderRules(initial)+'</div></details>'+
   '</div></div></article>';
}
let markets={};
function knownMarkets(){return markets;}
function render(){
  const container=$("#gl-content");
  if(!games.length){container.innerHTML='<div class="gl-empty">Nenhum confronto futuro atende aos métodos salvos para a próxima rodada. Tente outra data ou revise as condições no Nostradamus.</div>';
    $("#gl-actions").hidden=true;return;}
  const grouped=new Map();
  for(const g of games){if(!grouped.has(g.campeonato))grouped.set(g.campeonato,[]);grouped.get(g.campeonato).push(g);}
  container.innerHTML=[...grouped].map(([league,list])=>
    '<section class="gl-league"><h3>'+escapeHTML(league)+' <span>'+list.length+' jogos elegíveis</span></h3>'+
    list.map(renderGame).join("")+'</section>').join("");
  $("#gl-actions").hidden=false;
  updateSelected();
}
function updateSelected(){
  const checked=[...document.querySelectorAll(".gl-check:checked")];
  $("#gl-selection-count").textContent=checked.length+" jogo(s) marcado(s)";
  $("#gl-confirm").disabled=!checked.length;
}
$("#gl-content").addEventListener("change",e=>{
  if(e.target.matches(".gl-check")){updateSelected();return;}
  if(e.target.matches(".gl-method")){
    const card=e.target.closest(".gl-game"),id=Number(card.dataset.id);
    const game=games.find(g=>g.jogo_id===id);
    const method=game?.metodos.find(m=>String(m.metodo_idx)===e.target.value);
    if(method){
      card.querySelector(".gl-market").value=method.objetivo;
      card.querySelector(".gl-method-rules").innerHTML=renderRules(method);
    }
  }
});
async function search(e){
  e?.preventDefault();
  strategies=loadMethods();
  $("#gl-method-count").textContent=strategies.length+" método(s) salvo(s)";
  games=[];render();
  if(!strategies.length){status("Nenhum método salvo encontrado. Salve estratégias no Nostradamus, neste mesmo navegador.",true);return;}
  const date=$("#gl-date").value;
  const button=$("#gl-filter button[type=submit]");button.disabled=true;button.textContent="Consultando…";
  status("Verificando a próxima rodada e o histórico anterior a cada jogo.");
  try{
    const data=await post("/api/apostas/galileu/sinais",{data:date,estrategias:strategies});
    markets=data.objetivos||{};
    games=data.jogos||[];
    render();
    status(data.mensagem+" Encontrados "+games.length+" confronto(s) elegíveis.");
  }catch(err){status(err.message,true);}
  finally{button.disabled=false;button.textContent="Buscar jogos elegíveis";}
}
$("#gl-filter").addEventListener("submit",search);
$("#gl-confirm").addEventListener("click",async ()=>{
  const selected=[...document.querySelectorAll(".gl-check:checked")].map(el=>{
    const card=el.closest(".gl-game");
    return {
      jogo_id:Number(card.dataset.id),
      metodo_idx:Number(card.querySelector(".gl-method").value),
      objetivo:card.querySelector(".gl-market").value
    };
  });
  if(!selected.length)return;
  const text=selected.length===1?"1 entrada selecionada":selected.length+" entradas selecionadas";
  if(!window.confirm("CONFIRMAÇÃO DEFINITIVA\n\n"+text+
     ". O registro será permanente no Supabase e não poderá ser editado, cancelado ou excluído pela aplicação.\n\nConfirmar?"))return;
  const btn=$("#gl-confirm");btn.disabled=true;btn.textContent="Registrando…";
  try {
    const data=await post("/api/apostas/galileu/confirmar",{
       data:$("#gl-date").value,estrategias:strategies,apostas:selected
    });
    status(data.mensagem+" ("+data.registradas+" entrada(s)).");
    await refreshBank();
    await search();
  }catch(e){status(e.message,true);}
  finally{btn.textContent="Confirmar entradas selecionadas";updateSelected();}
});
(async()=>{await refreshBank();await search();})();
})();