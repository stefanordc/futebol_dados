/* Nostradamus: interface de estratégias históricas, sem chaves no navegador. */
(() => {
"use strict";
const $=q=>document.querySelector(q);
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt=(v,d=1)=>v==null||!Number.isFinite(Number(v))?"—":Number(v).toLocaleString("pt-BR",{minimumFractionDigits:d,maximumFractionDigits:d});
const store="df_nostradamus_estrategias_v1",status=$("#ns-feedback");
let meta=null,loaded=null,stored=[];
const today=new Date(),localToday=[today.getFullYear(),String(today.getMonth()+1).padStart(2,"0"),String(today.getDate()).padStart(2,"0")].join("-");
$("#ns-corte").max=localToday;
const prior=new Date(today.getFullYear(),today.getMonth(),today.getDate()-1);
$("#ns-corte").value=[prior.getFullYear(),String(prior.getMonth()+1).padStart(2,"0"),String(prior.getDate()).padStart(2,"0")].join("-");
const say=(s,error=false)=>{status.innerHTML='<div class="x1-message '+(error?"error":"info")+'">'+esc(s)+'</div>';};
const opts=(data,value)=>Object.entries(data).map(([id,n])=>'<option value="'+esc(id)+'" '+(value===id?'selected':'')+'>'+esc(n)+'</option>').join("");
function conditionLine(item={}){
  const id=crypto?.randomUUID?.()||String(Date.now()+Math.random());
  const div=document.createElement("div");div.className="ns-condition";div.dataset.row=id;
  div.innerHTML='<label>Indicador<select class="ns-metric" aria-label="Indicador">'+
    opts(meta.metricas,item.metrica||"xg")+'</select></label>'+
    '<label>Comparador<select class="ns-comparison" aria-label="Comparador">'+opts(meta.comparadores,item.comparador||"gt")+'</select></label>'+
    '<label>Margem (+ visitante)<input class="ns-margin" aria-label="Margem" type="number" step="0.01" value="'+esc(item.margem??0)+'"></label>'+
    '<button type="button" class="ns-remove" aria-label="Remover condição">Remover</button>';
  $("#ns-conditions").appendChild(div);drawCount();
}
function drawCount(){
  const n=$(".ns-conditions")?.children?.length||$("#ns-conditions").children.length;
  $("#ns-count").textContent=n+"/10 condições";
  $("#ns-add").disabled=n>=10;
}
const values=()=>({
  nome:$("#ns-nome").value.trim(),corte:$("#ns-corte").value,
  jogos:$("#ns-janela").value,campeonato_id:$("#ns-campeonato").value?Number($("#ns-campeonato").value):null,
  objetivo:$("#ns-objetivo").value,
  odd_hipotetica:$("#ns-odd").value?Number($("#ns-odd").value):null,
  comissao_pct:Number($("#ns-comissao").value),
  condicoes:[...$("#ns-conditions").children].map(row=>({
    metrica:row.querySelector(".ns-metric").value,
    comparador:row.querySelector(".ns-comparison").value,
    margem:Number(row.querySelector(".ns-margin").value)
  }))
});
function restore(saved){
  $("#ns-nome").value=saved.nome||"";
  $("#ns-corte").value=saved.corte||$("#ns-corte").value;
  $("#ns-janela").value=saved.jogos||"20";
  $("#ns-campeonato").value=saved.campeonato_id||"";
  $("#ns-objetivo").value=saved.objetivo||"back_mandante";
  $("#ns-odd").value=saved.odd_hipotetica??"";
  $("#ns-comissao").value=saved.comissao_pct??2;
  $("#ns-conditions").innerHTML="";
  (saved.condicoes||[]).slice(0,10).forEach(conditionLine);
  if(!$("#ns-conditions").children.length)conditionLine();
}
function renderSaved(){
  $("#ns-saved-list").innerHTML=stored.length?stored.map((s,i)=>
    '<div class="ns-saved-item"><div><strong>'+esc(s.nome)+'</strong>'+
    '<small>'+esc(meta?.objetivos?.[s.objetivo]||s.objetivo)+' · '+esc(s.jogos)+' jogos · '+esc(s.corte)+'</small></div>'+
    '<div class="ns-actions"><button type="button" data-load="'+i+'">Carregar</button>'+
    '<button type="button" data-delete="'+i+'" aria-label="Excluir '+esc(s.nome)+'">Excluir</button></div></div>').join(""):
    '<p class="x1-help">Nenhuma estratégia salva neste navegador.</p>';
}
$("#ns-saved-list").addEventListener("click",e=>{
  const load=e.target.closest("[data-load]"),del=e.target.closest("[data-delete]");
  if(load){restore(stored[Number(load.dataset.load)]);say("Estratégia carregada.");}
  if(del){stored.splice(Number(del.dataset.delete),1);localStorage.setItem(store,JSON.stringify(stored));renderSaved();}
});
$("#ns-add").addEventListener("click",()=>{if($("#ns-conditions").children.length<10)conditionLine();});
$("#ns-conditions").addEventListener("click",e=>{
  const btn=e.target.closest(".ns-remove");
  if(btn&&$("#ns-conditions").children.length>1){btn.closest(".ns-condition").remove();drawCount();}
});
$("#ns-save").addEventListener("click",()=>{
  if(!meta)return;
  const v=values();if(!v.nome||!v.corte||!v.condicoes.length){say("Dê um nome e escolha as condições.",true);return;}
  if(stored.length>=50){say("Limite de 50 estratégias locais.",true);return;}
  stored.push(v);
  try{localStorage.setItem(store,JSON.stringify(stored));renderSaved();say("Estratégia salva neste navegador.");}
  catch(e){say("Armazenamento local indisponível: "+e.message,true);}
});
function details(rows){
  if(!rows.length)return '<p class="x1-help">Nenhuma partida passou pelas condições.</p>';
  return '<div class="ns-scroll"><table class="ns-table"><thead><tr><th>Data</th><th>Jogo</th><th>Placar</th><th>Resultado</th><th>Odd</th><th>Unidades</th></tr></thead><tbody>'+
  rows.map(r=>'<tr><td>'+esc(r.data)+'</td><td><strong>'+esc(r.mandante)+' × '+esc(r.visitante)+'</strong>'+
    '<div class="ns-match-conditions">'+(r.condicoes||[]).map(c=>
      '<div>'+esc(c.nome)+': mandante <b>'+fmt(c.mandante,2)+'</b> '+esc(c.comparador)+' visitante <b>'+fmt(c.visitante,2)+'</b>'+
      (c.margem?' + '+fmt(c.margem,2):"")+'</div>').join("")+'</div></td>'+
    '<td>'+esc(r.placar)+'</td><td class="'+(r.green?"ns-green":"ns-red")+'">'+(r.green?"Green":"Red")+'</td>'+
    '<td>'+fmt(r.odd,2)+(r.tipo_odd==="hipotetica"?' (hip.)':"")+'</td><td>'+fmt(r.unidades,2)+'</td></tr>').join("")+
  '</tbody></table></div>';
}
function show(response){
  loaded=response;
  $("#ns-results").hidden=false;
  $("#ns-method").textContent=response.aviso;
  const body=$("#ns-summary");
  body.innerHTML=response.resultados.length?response.resultados.map((r,i)=>
    '<tr><td><button class="ns-expand" type="button" data-expand="'+i+'" aria-expanded="false" aria-label="Exibir jogos da liga '+esc(r.campeonato)+'">+</button></td>'+
    '<td>'+esc(r.campeonato)+'</td><td>'+fmt(r.entradas,0)+'</td>'+
    '<td class="ns-green">'+fmt(r.greens,0)+'</td><td class="ns-red">'+fmt(r.reds,0)+'</td>'+
    '<td>'+fmt(r.win_rate,1)+'%</td><td>'+fmt(r.cotadas,0)+'</td>'+
    '<td class="'+(r.unidades>=0?"ns-green":"ns-red")+'">'+fmt(r.unidades,2)+'</td></tr>').join(""):
    '<tr><td colspan="8">Nenhum jogo atende às condições com o histórico disponível.</td></tr>';
  $("#ns-details").innerHTML="";
  say("Análise concluída: "+response.entradas+" entradas históricas. Confira a cobertura das odds.");
}
$("#ns-summary").addEventListener("click",e=>{
  const btn=e.target.closest("[data-expand]");if(!btn||!loaded)return;
  const i=Number(btn.dataset.expand),r=loaded.resultados[i],out=$("#ns-details");
  const opened=btn.getAttribute("aria-expanded")==="true";
  $("#ns-summary").querySelectorAll(".ns-expand").forEach(el=>{el.textContent="+";el.setAttribute("aria-expanded","false");});
  if(opened){out.innerHTML="";return;}
  btn.textContent="−";btn.setAttribute("aria-expanded","true");
  out.innerHTML='<h3>Jogos selecionados · '+esc(r.campeonato)+'</h3>'+
    (r.entradas>r.jogos.length?'<p class="x1-help">Exibindo os primeiros '+r.jogos.length+' de '+r.entradas+' jogos para manter a página rápida.</p>':"")+
    details(r.jogos);
});
$("#ns-form").addEventListener("submit",async e=>{
  e.preventDefault();
  const config=values();
  if(config.condicoes.length>10||!config.condicoes.length){say("Adicione de 1 a 10 condições.",true);return;}
  const button=$("#ns-form button[type=submit]");button.disabled=true;button.textContent="Processando histórico…";
  $("#ns-results").hidden=true;say("Calculando as condições em ordem cronológica, sem dados futuros…");
  try{
    const r=await fetch("/api/apostas/nostradamus/testar",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(config)});
    const response=await r.json();
    if(!r.ok)throw new Error(typeof response.detail==="string"?response.detail:"Falha ao analisar os jogos.");
    show(response);
  }catch(e){say(e.message,true);}
  finally{button.disabled=false;button.textContent="Executar backtest";}
});
async function init(){
  try{
    const response=await fetch("/api/apostas/nostradamus/metadata");
    if(!response.ok)throw new Error("Não foi possível carregar os indicadores.");
    meta=await response.json();
    $("#ns-objetivo").innerHTML=opts(meta.objetivos,"back_mandante");
    $("#ns-campeonato").innerHTML='<option value="">Todos os campeonatos</option>'+
      (meta.ligas||[]).map(c=>'<option value="'+Number(c.id)+'">'+esc(c.nome)+'</option>').join("");
    conditionLine();
    try{const saved=JSON.parse(localStorage.getItem(store)||"[]");stored=Array.isArray(saved)?saved.slice(0,50):[];}
    catch{stored=[];}
    renderSaved();
  }catch(e){say(e.message,true);}
}
init();
})();