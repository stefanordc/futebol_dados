/* Nostradamus ao vivo: mesmos filtros, editor pré-jogo e IA da estratégia principal. */
(()=>{
"use strict";
const $=selector=>document.querySelector(selector);
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
}[c]));
const fmt=(value,decimals=0)=>value==null?"—":Number(value).toLocaleString("pt-BR",{
  minimumFractionDigits:decimals,maximumFractionDigits:decimals
});
const money=value=>value==null?"—":Number(value).toLocaleString("pt-BR",{
  style:"currency",currency:"BRL"
});
const cash=v=>v==null?"":Number(v)<0?"ns-red":"ns-green";
const rules=window.NostradamusRuleBuilder;
let metadata=null,lastSimulationConfig=null,aiSuggestions=[],undo=[],lastResult=null;

const yesterday=new Date();
yesterday.setDate(yesterday.getDate()-1);
const localDay=[yesterday.getFullYear(),
  String(yesterday.getMonth()+1).padStart(2,"0"),
  String(yesterday.getDate()).padStart(2,"0")].join("-");
$("#ns-inplay-corte").value=localDay;
$("#ns-inplay-corte").max=localDay;
$("#ns-inplay-mercado").disabled=true;

const numberOrNull=id=>{
  const raw=$(id).value.trim();
  return raw===""?null:Number(raw);
};
const feedback=(message,error=false)=>{
  $("#ns-inplay-feedback").textContent=message;
  $("#ns-inplay-feedback").classList.toggle("ns-inplay-error",error);
};
const selectedLeagues=()=>[...document.querySelectorAll("#ns-inplay-league-items input:checked")]
  .map(input=>Number(input.value));
function drawLeagues(){
  const all=[...document.querySelectorAll("#ns-inplay-league-items input")];
  const checked=all.filter(input=>input.checked);
  const count=checked.length;
  $("#ns-inplay-league-summary").textContent=count===all.length?
    "Todos os "+count+" campeonatos":count===0?"Nenhum campeonato selecionado":
    count===1?checked[0].dataset.nome:count+" campeonatos selecionados";
  $("#ns-inplay-league-all").classList.toggle("is-active",count===all.length);
  $("#ns-inplay-league-select-all").disabled=count===all.length;
}
function setAllLeagues(checked){
  document.querySelectorAll("#ns-inplay-league-items input").forEach(
    input=>{input.checked=checked;}
  );
  drawLeagues();
}
function closeLeagues(){
  $("#ns-inplay-league-options").hidden=true;
  $("#ns-inplay-league-trigger").setAttribute("aria-expanded","false");
}
$("#ns-inplay-league-trigger").addEventListener("click",()=>{
  const panel=$("#ns-inplay-league-options");
  panel.hidden=!panel.hidden;
  $("#ns-inplay-league-trigger").setAttribute("aria-expanded",String(!panel.hidden));
});
$("#ns-inplay-league-select-all").addEventListener("click",()=>setAllLeagues(true));
$("#ns-inplay-league-all").addEventListener("click",()=>{
  // Igual à aba principal: sem filtro = analisar todos.
  setAllLeagues(true);
  closeLeagues();
});
$("#ns-inplay-league-items").addEventListener("change",drawLeagues);
document.addEventListener("click",event=>{
  if(!$("#ns-inplay-league-control").contains(event.target))closeLeagues();
});
$("#ns-inplay-league-control").addEventListener("keydown",event=>{
  if(event.key==="Escape"){
    closeLeagues();
    $("#ns-inplay-league-trigger").focus();
  }
});
function params(){
  const goals={};
  for(const role of ["favorito","zebra","mandante","visitante"]){
    goals["gols_"+role]=numberOrNull("#ns-inplay-"+role);
    goals["gols_"+role+"_min"]=numberOrNull("#ns-inplay-"+role+"-min");
    goals["gols_"+role+"_max"]=numberOrNull("#ns-inplay-"+role+"-max");
  }
  return {
    corte:$("#ns-inplay-corte").value,
    jogos:$("#ns-inplay-janela").value,
    campeonato_ids:selectedLeagues(),
    minuto:numberOrNull("#ns-inplay-minuto"),
    vencendo:$("#ns-inplay-vencendo").value,
    diferenca_gols:numberOrNull("#ns-inplay-diferenca"),
    gols_total:numberOrNull("#ns-inplay-total"),
    ...goals,
    mercado:$("#ns-inplay-mercado").value,
    odd_hipotetica:numberOrNull("#ns-inplay-odd"),
    comissao_pct:4.5,
    condicoes:rules.read("#ns-inplay-conditions")
  };
}
function conditionCount(){
  rules.refresh("#ns-inplay-conditions");
}
$("#ns-inplay-add").addEventListener("click",()=>{
  if($("#ns-inplay-conditions").children.length>=10)return;
  rules.add("#ns-inplay-conditions");
});
$("#ns-inplay-conditions").addEventListener("change",event=>{
  const row=event.target.closest(".ns-condition");
  if(row)rules.update(row);
});
$("#ns-inplay-conditions").addEventListener("click",event=>{
  const button=event.target.closest(".ns-remove");
  if(!button)return;
  button.closest(".ns-condition").remove();
  conditionCount();
});
function escapeRow(game){
  return '<tr><td>'+esc(game.data)+'</td>'+
    '<td>'+esc(game.mandante+' × '+game.visitante)+
      (game.favorito?'<div class="ns-history-size">Favorito: '+esc(game.favorito)+'</div>':"")+
      '<div class="ns-match-conditions">'+(game.condicoes||[]).map(rule=>
        '<div><b>'+esc(rule.nome)+'</b>: '+
        (rule.tipo==="odd"?
          fmt(rule.odd,2)+' (mín. '+fmt(rule.odd_min,2)+' / máx. '+fmt(rule.odd_max,2)+')':
          rule.lado==="ambos"?fmt(rule.observado_mandante,2)+' / '+fmt(rule.observado_visitante,2):
          fmt(rule.observado,2)+' '+esc(rule.comparador)+' '+fmt(rule.comparado,2))+
        '</div>').join("")+'</div></td>'+
    '<td>'+esc(game.placar_minuto)+'</td>'+
    '<td>'+esc(game.placar_final)+'</td>'+
    '<td>'+esc(metadata?.objetivos?.[game.mercado]||game.mercado)+'</td>'+
    '<td class="'+(game.green?"ns-green":"ns-red")+'">'+(game.green?"Green":"Red")+'</td>'+
    '<td>'+fmt(game.odd,2)+'</td>'+
    '<td>'+fmt(game.unidades,3)+'</td>'+
    '<td class="'+cash(game.valor_reais)+'">'+money(game.valor_reais)+'</td></tr>';
}
function gameTable(games){
  return '<div class="ns-scroll"><table class="ns-table ns-inplay-table">'+
    '<thead><tr><th>Data</th><th>Partida / condições</th><th>Placar no minuto</th>'+
    '<th>Final</th><th>Mercado</th><th>Green / Red</th><th>Odd hipotética</th>'+
    '<th>Unidades</th><th>Lucro/prejuízo</th></tr></thead><tbody>'+
    games.map(escapeRow).join("")+'</tbody></table></div>';
}
function totalCells(x,league,expand=false,index=0){
  return '<tr>'+(expand?
    '<td><button class="ns-expand" type="button" data-inplay-expand="'+index+
      '" aria-expanded="false">+</button></td>':'<td></td>')+
    '<th scope="row">'+esc(league)+'</th><td>'+fmt(x.entradas)+'</td>'+
    '<td>'+fmt(x.greens)+'</td><td>'+fmt(x.reds)+'</td>'+
    '<td>'+fmt(x.win_rate,2)+'%</td>'+
    '<td>'+fmt(x.unidades,3)+'</td>'+
    '<td class="'+cash(x.valor_reais)+'">'+money(x.valor_reais)+'</td>'+
    '<td>'+fmt(x.odd_media,2)+'</td>'+
    '<td>'+money(x.lucro_medio_entrada)+'</td>'+
    '<td>'+fmt(x.maior_good_run)+'</td><td>'+fmt(x.maior_bad_run)+'</td></tr>';
}
function show(result){
  lastResult=result;
  const overall=result.total;
  $("#ns-inplay-results").hidden=false;
  $("#ns-inplay-kpis").innerHTML=[
    ["Entradas",fmt(overall.entradas)],
    ["Greens",fmt(overall.greens)],
    ["Reds",fmt(overall.reds)],
    ["Win rate",fmt(overall.win_rate,2)+"%"],
    ["Resultado hipotético",money(overall.valor_reais)],
    ["Odd média",fmt(overall.odd_media,2)],
    ["Maior good run",fmt(overall.maior_good_run)],
    ["Maior bad run",fmt(overall.maior_bad_run)]
  ].map(([label,value])=>
    '<div class="ns-inplay-kpi"><span>'+esc(label)+'</span><strong>'+esc(value)+'</strong></div>'
  ).join("");
  const rows=result.resultados||[];
  $("#ns-inplay-leagues").innerHTML=rows.map((x,index)=>totalCells(x,x.campeonato,true,index))
    .join("")||'<tr><td colspan="12">Nenhum jogo corresponde ao cenário informado.</td></tr>';
  $("#ns-inplay-total").innerHTML=totalCells(overall,"TOTAL",false);
  $("#ns-inplay-games").innerHTML="";
  $("#ns-inplay-coverage").textContent=
    "Jogos com gols auditados até a data de corte: "+fmt(result.jogos_com_placar_auditavel)+
    " · Jogos selecionados pelas condições: "+fmt(result.entradas)+
    " · Entradas cotadas: "+fmt(overall.cotadas)+"/"+fmt(overall.entradas)+
    ". Clique no + de um campeonato para ver os jogos, as regras e os placares.";
  $("#ns-inplay-warning").textContent=result.aviso||"";
  $("#ns-inplay-ai-output").innerHTML=
    '<p>Simulação concluída. Clique em Analisar oportunidades para sugerir regras baseadas no treino cronológico.</p>';
  aiSuggestions=[];
  undo.length=0;
  $("#ns-inplay-ai-undo").disabled=true;
  feedback("Simulação concluída: "+fmt(result.entradas)+" entrada(s) em "+fmt(rows.length)+" campeonato(s).");
}
$("#ns-inplay-leagues").addEventListener("click",event=>{
  const button=event.target.closest("[data-inplay-expand]");
  if(!button||!lastResult)return;
  const index=Number(button.dataset.inplayExpand);
  const selected=lastResult.resultados?.[index];
  if(!selected)return;
  const wasOpen=button.getAttribute("aria-expanded")==="true";
  $("#ns-inplay-leagues").querySelectorAll("[data-inplay-expand]").forEach(btn=>{
    btn.textContent="+";
    btn.setAttribute("aria-expanded","false");
  });
  $("#ns-inplay-games").innerHTML=wasOpen?"":'<h3>Jogos · '+esc(selected.campeonato)+'</h3>'+
    (selected.entradas>selected.jogos.length?
      '<p class="x1-help">Exibindo '+fmt(selected.jogos.length)+' de '+fmt(selected.entradas)+' jogos.</p>':"")+
    gameTable(selected.jogos);
  if(!wasOpen){
    button.textContent="−";
    button.setAttribute("aria-expanded","true");
  }
});
async function request(endpoint,config){
  const response=await fetch(endpoint,{
    method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(config)
  });
  const data=await response.json();
  if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:
    "Não foi possível realizar a análise.");
  return data;
}
$("#ns-inplay-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const config=params();
  if(!config.campeonato_ids.length){
    feedback("Selecione ao menos um campeonato.",true);
    return;
  }
  if(config.condicoes.length>10||config.condicoes.some(rules.invalid)){
    feedback("Verifique as regras pré-jogo: máximo 10 condições e valores obrigatórios válidos.",true);
    return;
  }
  const button=$("#ns-inplay-submit");
  button.disabled=true;
  $("#ns-inplay-results").hidden=true;
  feedback("Calculando o placar real por minuto e as estatísticas anteriores às partidas…");
  try{
    const result=await request("/api/apostas/nostradamus/ao-vivo/testar",config);
    lastSimulationConfig=JSON.parse(JSON.stringify(config));
    show(result);
  }catch(error){feedback(error.message,true);}
  finally{button.disabled=false;}
});
function score(x){
  if(!x||!x.entradas)return '<span class="ns-ai-muted">Sem entradas cotadas</span>';
  return '<strong class="'+cash(x.total_reais)+'">'+money(x.total_reais)+'</strong>'+
    ' <span class="ns-ai-muted">('+fmt(x.entradas)+' entradas · média '+
    money(x.media_reais)+'/entrada)</span>';
}
function drawAI(result){
  aiSuggestions=Array.isArray(result.sugestoes)?result.sugestoes:[];
  let html='<p class="ns-ai-explanation">'+esc(result.metodo||"")+" "+
    esc(result.mensagem||"")+'</p>';
  if(result.data_divisao){
    html+='<p class="ns-ai-muted">Fim do treino: '+esc(result.data_divisao)+
      ' · validação com jogos de datas posteriores.</p>';
  }
  if(result.base_treino||result.base_validacao){
    html+='<p class="ns-ai-muted">Base treino: '+score(result.base_treino)+
      ' · Base validação: '+score(result.base_validacao)+'</p>';
  }
  if(aiSuggestions.length){
    html+='<div class="ns-ai-list">'+aiSuggestions.map((item,index)=>
      '<article class="ns-ai-card"><h4>'+esc(item.descricao)+'</h4>'+
      '<div>Com alteração · treino: '+score(item.treino)+'</div>'+
      '<div>Com alteração · validação: '+score(item.validacao)+'</div>'+
      '<p>'+esc(item.avaliacao||"")+'</p>'+
      '<button type="button" class="ns-button secondary" data-inplay-ai-apply="'+index+'">'+
        (item.acao==="remover"?"Remover regra":"Adicionar regra")+'</button></article>'
    ).join("")+'</div>';
  }else{
    html+='<p class="ns-ai-empty">Nenhuma sugestão aprovada no treino. Não altere a estratégia sem evidência adicional.</p>';
  }
  html+='<p class="ns-ai-caution">'+esc(result.aviso||
    "A IA é análise retrospectiva baseada em odd hipotética, não previsão de lucro.")+'</p>';
  $("#ns-inplay-ai-output").innerHTML=html;
}
$("#ns-inplay-ai-run").addEventListener("click",async()=>{
  if(!lastSimulationConfig)return;
  const button=$("#ns-inplay-ai-run");
  button.disabled=true;
  button.textContent="Analisando histórico…";
  $("#ns-inplay-ai-output").textContent=
    "Testando condições pré-jogo no histórico de treino e validação…";
  try{
    const output=await request(
      "/api/apostas/nostradamus/ao-vivo/otimizar",lastSimulationConfig);
    drawAI(output);
  }catch(error){
    $("#ns-inplay-ai-output").textContent=error.message;
  }finally{
    button.disabled=false;
    button.textContent="Analisar oportunidades";
  }
});
$("#ns-inplay-ai-go-conditions").addEventListener("click",()=>{
  $("#ns-inplay-conditions").scrollIntoView({behavior:"smooth",block:"start"});
});
$("#ns-inplay-ai-test-shortcut").addEventListener("click",()=>{
  $("#ns-inplay-form").requestSubmit();
});
$("#ns-inplay-ai-undo").addEventListener("click",()=>{
  const previous=undo.pop();
  if(!previous)return;
  rules.clear("#ns-inplay-conditions");
  previous.forEach(item=>rules.add("#ns-inplay-conditions",item));
  conditionCount();
  $("#ns-inplay-ai-undo").disabled=!undo.length;
  feedback("Última alteração da IA desfeita. Refaça o backtest para atualizar os resultados.");
});
$("#ns-inplay-ai-output").addEventListener("click",event=>{
  const button=event.target.closest("[data-inplay-ai-apply]");
  if(!button||button.disabled)return;
  const item=aiSuggestions[Number(button.dataset.inplayAiApply)];
  if(!item)return;
  const current=rules.read("#ns-inplay-conditions");
  if(item.acao==="remover"){
    if(item.indice<0||item.indice>=current.length){
      feedback("As regras foram modificadas. Execute outra análise da IA.",true);
      return;
    }
    if(lastSimulationConfig?.condicoes?.length!==current.length){
      feedback("As regras foram modificadas. Execute outra análise da IA.",true);
      return;
    }
    undo.push(current);
    $("#ns-inplay-conditions").children[item.indice].remove();
    conditionCount();
  }else{
    if(current.length>=10){
      feedback("Você já atingiu o limite de 10 condições.",true);
      return;
    }
    if(current.some(rule=>JSON.stringify(rule)===JSON.stringify(item.condicao))){
      feedback("A condição sugerida já existe.",true);
      return;
    }
    undo.push(current);
    rules.add("#ns-inplay-conditions",item.condicao);
  }
  $("#ns-inplay-ai-undo").disabled=false;
  button.disabled=true;
  button.textContent=item.acao==="remover"?"Regra removida":"Regra adicionada";
  feedback("Condição modificada no formulário. Teste novamente ou desfaça a mudança.");
  $("#ns-inplay-conditions").scrollIntoView({behavior:"smooth",block:"start"});
});
async function initialize(){
  try{
    if(!rules)throw Error("O editor de condições do Nostradamus não foi carregado.");
    const response=await fetch("/api/apostas/nostradamus/metadata",{cache:"no-store"});
    if(!response.ok)throw Error("Falha ao carregar ligas e indicadores.");
    metadata=await response.json();
    rules.setMeta(metadata);
    $("#ns-inplay-league-items").innerHTML=(metadata.ligas||[]).map(item=>
      '<label class="ns-league-option"><input type="checkbox" checked value="'+Number(item.id)+
      '" data-nome="'+esc(item.nome)+'"><span>'+esc(item.nome)+'</span></label>'
    ).join("");
    drawLeagues();
    const markets=Object.entries(metadata.objetivos||{});
    $("#ns-inplay-mercado").innerHTML=markets.map(([key,label])=>
      '<option value="'+esc(key)+'"'+(key==="lay_empate"?" selected":"")+'>'+
      esc(label)+'</option>').join("");
    $("#ns-inplay-mercado").disabled=false;
    conditionCount();
  }catch(error){feedback(error.message,true);}
}
initialize();
})();
