/* Nostradamus: interface de estratégias históricas, sem chaves no navegador. */
(() => {
"use strict";
const $=q=>document.querySelector(q);
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt=(v,d=1)=>v==null||!Number.isFinite(Number(v))?"—":Number(v).toLocaleString("pt-BR",{minimumFractionDigits:d,maximumFractionDigits:d});
const money=v=>v==null||!Number.isFinite(Number(v))?"—":Number(v).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const pnlClass=v=>v==null?"":Number(v)>=0?"ns-green":"ns-red";
const oddLabel=r=>r.tipo_odd==="lay_estimado"?"Lay estimado":r.tipo_odd==="api_casa"?"Casa / histórico":r.tipo_odd==="hipotetica"?"Hipotética":r.tipo_odd==="registrada_antes"?"FotMob pré-jogo":"";

const store="df_nostradamus_estrategias_v1",status=$("#ns-feedback");
let meta=null,loaded=null,stored=[],editing=null;
const today=new Date(),localToday=[today.getFullYear(),String(today.getMonth()+1).padStart(2,"0"),String(today.getDate()).padStart(2,"0")].join("-");
$("#ns-corte").max=localToday;
const prior=new Date(today.getFullYear(),today.getMonth(),today.getDate()-1);
$("#ns-corte").value=[prior.getFullYear(),String(prior.getMonth()+1).padStart(2,"0"),String(prior.getDate()).padStart(2,"0")].join("-");
const say=(s,error=false)=>{status.innerHTML='<div class="x1-message '+(error?"error":"info")+'">'+esc(s)+'</div>';};
const opts=(data,value)=>Object.entries(data).map(([id,n])=>'<option value="'+esc(id)+'" '+(value===id?'selected':'')+'>'+esc(n)+'</option>').join("");
const metricOpts=(data,value)=>{
  const normal={},physical={};
  Object.entries(data).forEach(([id,name])=>{
    if(name.startsWith("Dados físicos · "))physical[id]=name.slice("Dados físicos · ".length);
    else normal[id]=name;
  });
  return '<optgroup label="Estatísticas de jogo">'+opts(normal,value)+'</optgroup>'+
         '<optgroup label="Dados físicos">'+opts(physical,value)+'</optgroup>';
};
function normalizeCondition(item={}){
  if(item.tipo==="odd"){
    return {tipo:"odd",mercado:item.mercado||"over_25",
      odd_min:item.odd_min??"",odd_max:item.odd_max??""};
  }
  // Os rótulos legados são reinterpretados como papéis dinâmicos,
  // nunca fixados no mando original.
  const oldRecord=Object.keys(item).length>0;
  const legacyRole={mandante:"favorito",visitante:"zebra"};
  const lado=legacyRole[item.lado]||(
    ["favorito","zebra","ambos"].includes(item.lado)?item.lado:"favorito");
  const metrica=item.metrica||"xg";
  const opponent=lado==="zebra"?"favorito":"zebra";
  const originalRef=item.referencia;
  const referencia=legacyRole[originalRef]||originalRef||
    (oldRecord&&lado!=="ambos"?opponent:"valor");
  const metricaRef=item.metrica_ref||metrica;
  const valor=item.valor??item.margem??(oldRecord?0:"");
  let modo;
  if(referencia==="valor")modo="valor";
  else if(referencia==="adversario"||
    (referencia===opponent&&metricaRef===metrica&&Number(valor)===0)){
    modo="adversario";
  }else modo="legado";
  const mandoPreferido=["mandante","visitante","indiferente"].includes(item.mando_preferido)
    ?item.mando_preferido:"indiferente";
  return {tipo:"indicador",lado,
    mando_preferido:lado==="ambos"?"indiferente":mandoPreferido,
    metrica,comparador:item.comparador||"gt",modo,
    referencia:modo==="legado"?referencia:opponent,metrica_ref:metricaRef,valor};
}
function updateConditionRow(row){
  const isOdd=row.querySelector(".ns-condition-kind").value==="odd";
  row.querySelectorAll(".ns-stat-criterion").forEach(field=>{
    field.hidden=isOdd;
    field.querySelectorAll("input,select").forEach(input=>{input.disabled=isOdd;});
  });
  row.querySelectorAll(".ns-odd-criterion").forEach(field=>{
    field.hidden=!isOdd;
    field.querySelectorAll("input,select").forEach(input=>{input.disabled=!isOdd;});
  });
  if(isOdd)return;
  const ref=row.querySelector(".ns-reference");
  const both=row.querySelector(".ns-side").value==="ambos";
  const mando=row.querySelector(".ns-home-filter");
  if(both)mando.value="indiferente";
  mando.disabled=both;
  mando.title=both
    ?"Ambos exige as duas equipes e utiliza mando indiferente."
    :"Filtrar partidas pelo mando do favorito ou da zebra.";
  for(const option of ref.options){
    option.disabled=both&&option.value!=="valor";
  }
  if(both&&ref.value!=="valor")ref.value="valor";
  const mode=ref.value;
  const fixed=mode==="valor",legacy=mode==="legado";
  const valueWrap=row.querySelector(".ns-value-wrap");
  const legacyMetric=row.querySelector(".ns-refmetric-wrap");
  const legacySide=row.querySelector(".ns-legacy-side-wrap");
  const value=row.querySelector(".ns-value");
  valueWrap.hidden=!fixed&&!legacy;
  legacyMetric.hidden=!legacy;
  legacySide.hidden=!legacy;
  for(const el of legacyMetric.querySelectorAll("select"))el.disabled=!legacy;
  for(const el of legacySide.querySelectorAll("select"))el.disabled=!legacy;
  value.disabled=!fixed&&!legacy;
  value.required=fixed||legacy;
  if(legacy&&value.value==="")value.value="0";
  row.querySelector(".ns-value-label").textContent=legacy?"Ajuste da regra antiga":"Valor absoluto";
  value.placeholder=fixed?"Ex.: 1,5":"Ex.: 0";
  value.setAttribute("aria-label",legacy?"Ajuste da regra antiga":"Valor absoluto");
}
function missingConditionValue(condition){
  if(condition.tipo==="odd"){
    const min=condition.odd_min,max=condition.odd_max;
    return !condition.mercado||(min==null&&max==null)||
      (min!=null&&(!Number.isFinite(min)||min<1.01||min>1000))||
      (max!=null&&(!Number.isFinite(max)||max<1.01||max>1000))||
      (min!=null&&max!=null&&min>max);
  }
  // "Mesmo indicador do adversário" não tem, nem precisa ter, valor numérico.
  return condition.referencia!=="adversario" &&
    (condition.valor==null||!Number.isFinite(condition.valor));
}
function conditionLine(item={}){
  const data=normalizeCondition(item);
  const id=String(Date.now())+"-"+Math.random().toString(36).slice(2,9);
  const div=document.createElement("div");div.className="ns-condition";div.dataset.row=id;
  const modes={valor:"Valor absoluto",adversario:"Mesmo indicador do adversário"};
  if(data.modo==="legado")modes.legado="Regra personalizada (salva anteriormente)";
  div.innerHTML=
    '<label class="ns-kind-field">Tipo de critério<select class="ns-condition-kind" aria-label="Tipo de critério">'+
      opts({indicador:"Estatística das equipes",odd:"Odd de um mercado"},data.tipo||"indicador")+'</select></label>'+
    '<label class="ns-stat-criterion">Equipe analisada<select class="ns-side" aria-label="Equipe analisada">'+
      opts({favorito:"Favorito (menor odd)",zebra:"Zebra (maior odd)",ambos:"Ambos (cada equipe)"},data.lado||"favorito")+'</select></label>'+
    '<label class="ns-stat-criterion ns-home-filter-wrap">Mando de campo<select class="ns-home-filter" aria-label="Mando de campo">'+
      opts({indiferente:"Indiferente",mandante:"Mandante",visitante:"Visitante"},data.mando_preferido||"indiferente")+'</select></label>'+
    '<label class="ns-stat-criterion">Indicador<select class="ns-metric" aria-label="Indicador">'+
      metricOpts(meta.metricas,data.metrica)+'</select></label>'+
    '<label class="ns-stat-criterion">Comparador<select class="ns-comparison" aria-label="Comparador">'+
      opts(meta.comparadores,data.comparador)+'</select></label>'+
    '<button type="button" class="ns-remove" aria-label="Remover condição">Remover</button>'+
    '<label class="ns-reference-wrap ns-stat-criterion">Comparar com<select class="ns-reference" aria-label="Comparar com">'+
      opts(modes,data.modo)+'</select></label>'+
    '<label class="ns-value-wrap ns-stat-criterion"><span class="ns-value-label">Valor absoluto</span>'+
      '<input class="ns-value" type="number" inputmode="decimal" min="-10000" max="10000" step="any" value="'+
      esc(data.modo==="valor"?data.valor:data.modo==="legado"?data.valor:"")+'"></label>'+
    '<label class="ns-legacy-side-wrap ns-stat-criterion" hidden>Referência original<select class="ns-legacy-side" aria-label="Referência original">'+
      opts({favorito:"Favorito",zebra:"Zebra"},data.referencia)+'</select></label>'+
    '<label class="ns-refmetric-wrap ns-stat-criterion" hidden>Indicador original<select class="ns-reference-metric" aria-label="Indicador original">'+
      metricOpts(meta.metricas,data.metrica_ref)+'</select></label>'+
    '<label class="ns-odd-criterion" hidden>Mercado da odd<select class="ns-odd-market" aria-label="Mercado da odd" required>'+
      opts(meta.mercados_odd||{},data.mercado||"over_25")+'</select></label>'+
    '<label class="ns-odd-criterion" hidden>Odd mínima (opcional)<input class="ns-odd-min" aria-label="Odd mínima" type="number" step="any" min="1.01" max="1000" placeholder="Ex.: 1,70" value="'+
      esc(data.odd_min??"")+'"></label>'+
    '<label class="ns-odd-criterion" hidden>Odd máxima (opcional)<input class="ns-odd-max" aria-label="Odd máxima" type="number" step="any" min="1.01" max="1000" placeholder="Ex.: 2,50" value="'+
      esc(data.odd_max??"")+'"></label>';
  $("#ns-conditions").appendChild(div);
  updateConditionRow(div);
  drawCount();
}
function drawCount(){
  const n=$(".ns-conditions")?.children?.length||$("#ns-conditions").children.length;
  $("#ns-count").textContent=n+"/10 condições";
  $("#ns-add").disabled=n>=10;
}
// Dropdown de checkboxes: sem seleção = todos os campeonatos.
const selectedLeagues=()=>[...document.querySelectorAll("#ns-league-items input:checked")]
  .map(input=>Number(input.value));
function drawLeagues(){
  const ids=selectedLeagues();
  const total=document.querySelectorAll("#ns-league-items input").length;
  const names=[...document.querySelectorAll("#ns-league-items input:checked")]
    .map(el=>el.dataset.nome);
  const summary=$("#ns-league-summary");
  summary.textContent=!ids.length?"Todos os campeonatos":
    ids.length===1?names[0]:
    ids.length===total?"Todos os "+total+" campeonatos":
    ids.length+" campeonatos selecionados";
  $("#ns-league-all").classList.toggle("is-active",!ids.length);
  const allButton=$("#ns-league-select-all");
  allButton.disabled=total===0||ids.length===total;
  allButton.setAttribute("aria-label",total>0?
    "Selecionar todos os "+total+" campeonatos":"Nenhum campeonato disponível");
}
function setLeagues(ids){
  const wanted=new Set(Array.isArray(ids)?ids.map(Number):[]);
  document.querySelectorAll("#ns-league-items input").forEach(input=>{
    input.checked=wanted.has(Number(input.value));
  });
  drawLeagues();
}
function closeLeagues(){
  $("#ns-league-options").hidden=true;
  $("#ns-league-trigger").setAttribute("aria-expanded","false");
}
$("#ns-league-trigger").addEventListener("click",()=>{
  const options=$("#ns-league-options");
  options.hidden=!options.hidden;
  $("#ns-league-trigger").setAttribute("aria-expanded",String(!options.hidden));
});
$("#ns-league-all").addEventListener("click",()=>{
  setLeagues([]);
  closeLeagues();
  $("#ns-league-trigger").focus();
});
$("#ns-league-select-all").addEventListener("click",()=>{
  const ids=[...document.querySelectorAll("#ns-league-items input[type=checkbox]")]
    .map(input=>Number(input.value));
  setLeagues(ids);
  // Mantém a lista aberta para verificar que todos os clubes foram marcados.
});
$("#ns-league-items").addEventListener("change",drawLeagues);
document.addEventListener("click",event=>{
  if(!$("#ns-league-control").contains(event.target))closeLeagues();
});
$("#ns-league-control").addEventListener("keydown",event=>{
  if(event.key==="Escape"){
    closeLeagues();
    $("#ns-league-trigger").focus();
  }
});
const values=()=>({
  nome:$("#ns-nome").value.trim(),corte:$("#ns-corte").value,
  jogos:$("#ns-janela").value,campeonato_ids:selectedLeagues(),
  objetivo:$("#ns-objetivo").value,
  odd_hipotetica:$("#ns-odd").value?Number($("#ns-odd").value):null,
  comissao_pct:4.5,
  condicoes:[...$("#ns-conditions").children].map(row=>{
    if(row.querySelector(".ns-condition-kind").value==="odd"){
      const min=row.querySelector(".ns-odd-min").value.trim();
      const max=row.querySelector(".ns-odd-max").value.trim();
      return {tipo:"odd",mercado:row.querySelector(".ns-odd-market").value,
        odd_min:min===""?null:Number(min),odd_max:max===""?null:Number(max)};
    }
    const mode=row.querySelector(".ns-reference").value;
    const base={
      lado:row.querySelector(".ns-side").value,
      mando_preferido:row.querySelector(".ns-home-filter").value,
      metrica:row.querySelector(".ns-metric").value,
      comparador:row.querySelector(".ns-comparison").value
    };
    if(mode==="adversario")return {...base,referencia:"adversario"};
    const raw=row.querySelector(".ns-value").value.trim();
    const valor=raw===""?null:Number(raw);
    if(mode==="valor")return {...base,referencia:"valor",valor};
    return {...base,referencia:row.querySelector(".ns-legacy-side").value,
      metrica_ref:row.querySelector(".ns-reference-metric").value,valor};
  })
});
function restore(saved){
  $("#ns-nome").value=saved.nome||"";
  $("#ns-corte").value=saved.corte||$("#ns-corte").value;
  $("#ns-janela").value=saved.jogos||"20";
  setLeagues(Array.isArray(saved.campeonato_ids)&&saved.campeonato_ids.length
    ?saved.campeonato_ids:(saved.campeonato_id?[saved.campeonato_id]:[]));
  $("#ns-objetivo").value=saved.objetivo||"back_favorito";
  $("#ns-odd").value=saved.odd_hipotetica??"";
  $("#ns-comissao").value="4.5";
  $("#ns-conditions").innerHTML="";
  (saved.condicoes||[]).slice(0,10).forEach(conditionLine);
  if(!$("#ns-conditions").children.length)conditionLine();
}
function setTab(tab){
  const saved=tab==="salvas";
  $("#ns-workbench").hidden=saved;
  $("#ns-saved").hidden=!saved;
  document.querySelectorAll("[data-ns-tab]").forEach(b=>{
    const active=b.dataset.nsTab===tab;
    b.classList.toggle("is-active",active);
    b.setAttribute("aria-selected",String(active));
  });
}
document.querySelector(".ns-subtabs").addEventListener("click",event=>{
  const btn=event.target.closest("[data-ns-tab]");
  if(btn)setTab(btn.dataset.nsTab);
});
function roleLabel(role,mando){
  if(role==="ambos")return "Ambos (cada equipe)";
  if(role==="favorito"||role==="zebra"){
    const name=role==="favorito"?"Favorito":"Zebra";
    return name+(mando?" ("+(mando==="mandante"?"Mandante":"Visitante")+")":" (pela odd)");
  }
  return role==="visitante"?"Visitante (estratégia antiga)":"Mandante (estratégia antiga)";
}
function formatRule(rule){
  if(rule.tipo==="odd"){
    const name=meta?.mercados_odd?.[rule.mercado]||rule.mercado;
    const bounds=[rule.odd_min!=null?"mín. "+fmt(rule.odd_min,2):"",
      rule.odd_max!=null?"máx. "+fmt(rule.odd_max,2):""].filter(Boolean);
    return esc("Odd de "+name+" · "+bounds.join(" · "));
  }
  const mando=rule.mando_preferido&&rule.mando_preferido!=="indiferente"
    ?" · "+(rule.mando_preferido==="mandante"?"Mandante":"Visitante"):"";
  const lhs=roleLabel(rule.lado)+mando+" · "+
    (meta?.metricas?.[rule.metrica]||rule.metrica);
  const rhs=rule.referencia==="valor"?fmt(rule.valor,2):
    rule.referencia==="adversario"?"mesmo indicador do adversário":
      roleLabel(rule.referencia)+" · "+
      (meta?.metricas?.[rule.metrica_ref||rule.metrica]||rule.metrica_ref)+
      (Number(rule.valor)?" + "+fmt(rule.valor,2):"");
  return esc(lhs+" "+(meta?.comparadores?.[rule.comparador]||rule.comparador)+" "+rhs);
}
function dateSaved(value){
  if(!value)return "—";
  const date=new Date(value);
  if(Number.isNaN(date.getTime()))return "—";
  return new Intl.DateTimeFormat("pt-BR",{
    timeZone:"America/Sao_Paulo",
    day:"2-digit",month:"2-digit",year:"numeric",
    hour:"2-digit",minute:"2-digit",hourCycle:"h23"
  }).format(date).replace(", "," às ");
}
function renderSaved(){
  const target=$("#ns-saved-list");
  if(!stored.length){
    target.innerHTML='<div class="ns-saved-empty"><strong>Nenhuma estratégia cadastrada no Supabase.</strong>'+
      '<p>Para aparecer nesta lista, salve uma estratégia em “Simular estratégia”. Se você tinha métodos antigos, abra o Nostradamus no mesmo navegador em que foram criados para tentar importar os dados.</p></div>';
    return;
  }
  target.innerHTML='<div class="ns-saved-count">'+stored.length+
    (stored.length===1?" estratégia cadastrada":" estratégias cadastradas")+'</div>'+
    '<div class="ns-saved-table-wrap"><table class="ns-saved-table" aria-label="Estratégias salvas no Supabase">'+
    '<thead><tr><th scope="col">Estratégia</th><th scope="col">Data de criação</th>'+
    '<th scope="col">Última atualização</th><th scope="col">Objetivo</th>'+
    '<th scope="col">Ações</th></tr></thead><tbody>'+
    stored.map(s=>'<tr><td><div class="ns-strategy-name">'+esc(s.nome)+'</div>'+
      '<span class="ns-strategy-sub">'+esc(s.jogos)+" jogos · "+
        s.condicoes.length+' regra(s) · Versão '+esc(s.versao)+'</span></td>'+
      '<td><time datetime="'+esc(s.criado_em||"")+'">'+esc(dateSaved(s.criado_em))+'</time></td>'+
      '<td><time datetime="'+esc(s.atualizado_em||"")+'">'+esc(dateSaved(s.atualizado_em))+'</time></td>'+
      '<td>'+esc(meta?.objetivos?.[s.objetivo]||s.objetivo)+'</td>'+
      '<td><div class="ns-saved-row-actions"><button type="button" data-rules="'+s.id+
        '" aria-controls="ns-rules-'+s.id+'" aria-expanded="false">Ver regras</button>'+
        '<button type="button" data-edit="'+s.id+'">Editar</button></div></td></tr>'+
      '<tr class="ns-saved-details" id="ns-rules-'+s.id+'" hidden><td colspan="5">'+
      '<div class="ns-saved-details-title">Condições · '+esc(s.nome)+'</div>'+
      '<ol class="ns-db-rules">'+s.condicoes.map(r=>'<li>'+formatRule(r)+'</li>').join("")+'</ol>'+
      '</td></tr>').join("")+'</tbody></table></div>';
}
$("#ns-saved-list").addEventListener("click",event=>{
  const rules=event.target.closest("[data-rules]");
  if(rules){
    const panel=document.getElementById("ns-rules-"+rules.dataset.rules);
    if(!panel)return;
    const isOpen=rules.getAttribute("aria-expanded")==="true";
    panel.hidden=isOpen;
    rules.setAttribute("aria-expanded",String(!isOpen));
    rules.textContent=isOpen?"Ver regras":"Ocultar regras";
    return;
  }
  const edit=event.target.closest("[data-edit]");
  if(!edit)return;
  const s=stored.find(row=>String(row.id)===edit.dataset.edit);
  if(!s)return;
  editing={id:s.id,versao:s.versao};
  restore(s);
  $("#ns-editing").hidden=false;
  $("#ns-editing-name").textContent="Editando: "+s.nome+" (versão "+s.versao+")";
  $("#ns-save").textContent="Salvar alterações";
  setTab("simular");
  say("Altere as condições e clique em Salvar alterações.");
  $("#ns-form").scrollIntoView({behavior:"smooth",block:"start"});
});
function resetEditing(){
  editing=null;
  $("#ns-editing").hidden=true;
  $("#ns-save").textContent="Salvar estratégia";
  $("#ns-nome").value="";
  setLeagues([]);
  closeLeagues();
  $("#ns-conditions").innerHTML="";
  conditionLine();
}
$("#ns-new").addEventListener("click",resetEditing);
$("#ns-create").addEventListener("click",()=>{
  resetEditing();
  setTab("simular");
  $("#ns-nome").focus();
});
async function api(url,options){
  const r=await fetch(url,options);
  const data=await r.json();
  if(!r.ok)throw Error(typeof data.detail==="string"?data.detail:"Falha ao consultar o banco.");
  return data;
}
const jsonPost=(method,data)=>({method,headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
async function fetchSaved(){
  // Evita reutilizar resposta GET antiga após uma criação/edição.
  const data=await api("/api/apostas/nostradamus/estrategias",{cache:"no-store"});
  if(!Array.isArray(data))throw Error("A consulta ao banco não retornou uma lista válida.");
  stored=data;
  renderSaved();
}
async function importLegacy(){
  const original=localStorage.getItem(store);
  if(!original)return;
  let legacy;
  try{legacy=JSON.parse(original);}
  catch(e){say("Estratégias antigas não estão em JSON válido; preservadas no navegador.",true);return;}
  if(!Array.isArray(legacy)||!legacy.length){
    localStorage.removeItem(store);
    return;
  }
  try{
    const response=await api("/api/apostas/nostradamus/estrategias/importar",
      jsonPost("POST",{estrategias:legacy}));
    await fetchSaved();
    localStorage.removeItem(store);
    say("Migração concluída: "+response.importadas+" estratégia(s) enviada(s) ao Supabase. "+
      response.existentes+" já existia(m).");
  }catch(e){
    say("Não foi possível migrar as estratégias antigas: "+e.message+
      ". A cópia antiga foi preservada até concluir a importação.",true);
  }
}
$("#ns-add").addEventListener("click",()=>{if($("#ns-conditions").children.length<10)conditionLine();});
$("#ns-conditions").addEventListener("change",e=>{
  const row=e.target.closest(".ns-condition");
  if(row)updateConditionRow(row);
});
$("#ns-conditions").addEventListener("click",e=>{
  const btn=e.target.closest(".ns-remove");
  if(btn&&$("#ns-conditions").children.length>1){btn.closest(".ns-condition").remove();drawCount();}
});
$("#ns-save").addEventListener("click",async ()=>{
  if(!meta)return;
  const v=values();
  if(!v.nome){say("Informe um nome para salvar no Supabase.",true);$("#ns-nome").focus();return;}
  if(!v.corte||!v.condicoes.length||v.condicoes.some(missingConditionValue)){
    say("Preencha a data e valores numéricos das condições com Valor absoluto.",true);return;
  }
  const btn=$("#ns-save");btn.disabled=true;btn.textContent="Salvando no banco…";
  try{
    const endpoint=editing?
      "/api/apostas/nostradamus/estrategias/"+editing.id:
      "/api/apostas/nostradamus/estrategias";
    const saved=await api(endpoint,jsonPost(editing?"PATCH":"POST",
      editing?{...v,versao:editing.versao}:v));
    await fetchSaved();
    // A criação só é considerada concluída após ler o próprio registro do banco.
    const confirmed=stored.find(item=>Number(item.id)===Number(saved.id)
       && Number(item.versao)===Number(saved.versao));
    if(!confirmed){
      throw Error("O servidor respondeu ao salvamento, mas a estratégia não apareceu na consulta ao Supabase. Verifique a conexão antes de tentar novamente.");
    }
    editing=null;
    $("#ns-editing").hidden=true;
    setTab("salvas");
    say("Estratégia "+saved.nome+" confirmada no Supabase.");
  }catch(e){say(e.message,true);}
  finally{btn.disabled=false;btn.textContent=editing?"Salvar alterações":"Salvar estratégia";}
});
function matchLabel(r){
  if(r.favorito){
    return '<strong>Favorito ('+esc(r.mando_favorito==="mandante"?"Mandante":"Visitante")+'): '+
      esc(r.favorito)+'</strong> · <strong>Zebra ('+
      esc(r.mando_zebra==="mandante"?"Mandante":"Visitante")+'): '+
      esc(r.zebra)+'</strong>'+
      '<div class="ns-match-odds">Match Odds: favorito '+fmt(r.odd_favorito,2)+
      ' · zebra '+fmt(r.odd_zebra,2)+'</div>';
  }
  return '<strong>Sem classificação por odds</strong> · '+esc(r.mandante)+
    ' (mandante) × '+esc(r.visitante)+' (visitante)';
}
function details(rows){
  if(!rows.length)return '<p class="x1-help">Nenhuma partida passou pelas condições.</p>';
  return '<div class="ns-scroll"><table class="ns-table"><thead><tr><th>Data</th><th>Jogo</th><th>Placar</th><th>Resultado</th><th>Odd / origem</th><th>Unidades (u)</th><th>Resultado (R$)</th></tr></thead><tbody>'+
  rows.map(r=>'<tr><td>'+esc(r.data)+'</td><td>'+matchLabel(r)+
    '<div class="ns-history-size">Histórico anterior: '+fmt(r.historico_mandante,0)+' jogos do mandante · '+fmt(r.historico_visitante,0)+' do visitante</div>'+
    '<div class="ns-match-conditions">'+(r.condicoes||[]).map(c=>
      c.tipo==="odd"?
      '<div><b>Odd · '+esc(c.nome)+'</b>: '+fmt(c.odd,2)+
      ' (mín. '+fmt(c.odd_min,2)+' / máx. '+fmt(c.odd_max,2)+
      ') · '+esc(c.fonte==="lay_estimado"?"Lay estimado":"Odd do banco")+'</div>':
      '<div><b>'+esc(roleLabel(c.lado,c.mando))+'</b>'+
      (c.mando_preferido&&c.mando_preferido!=="indiferente"?
        ' · Filtro: '+esc(c.mando_preferido==="mandante"?"Mandante":"Visitante"):"")+
      ' · '+esc(c.nome)+
      ': <b>'+(c.lado==="ambos"?
      'Mandante '+fmt(c.observado_mandante,2)+' / Visitante '+fmt(c.observado_visitante,2):
      fmt(c.observado,2))+'</b> '+esc(c.comparador)+
      ' <b>'+fmt(c.comparado,2)+'</b> ('+
      (c.referencia==="valor"?"valor absoluto":c.referencia==="adversario"?
      "mesmo indicador do adversário":esc(c.referencia)+" · "+esc(c.nome_ref)+
      (Number(c.valor)?" + ajuste "+fmt(c.valor,2):""))+')</div>').join("")+'</div></td>'+
    '<td>'+esc(r.placar_favorito||r.placar)+
    '<div class="ns-match-odds">'+(r.favorito?"Favorito × zebra":"Mandante × visitante")+
    '</div></td><td class="'+(r.green?"ns-green":"ns-red")+'">'+(r.green?"Green":"Red")+'</td>'+
    '<td>'+fmt(r.odd,2)+(r.tipo_odd?
        '<div class="ns-odd-origin">'+esc(oddLabel(r))+
        (r.bookmaker?' · '+esc(r.bookmaker):'')+'</div>':"")+'</td>'+
    '<td class="'+pnlClass(r.unidades)+'">'+fmt(r.unidades,2)+'</td>'+
    '<td class="'+pnlClass(r.valor_reais)+'">'+money(r.valor_reais)+'</td></tr>').join("")+
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
    '<td>'+fmt(r.win_rate,1)+'%</td>'+
    '<td class="'+pnlClass(r.unidades)+'">'+fmt(r.unidades,2)+'</td>'+
    '<td class="'+pnlClass(r.valor_reais)+'">'+money(r.valor_reais)+'</td>'+
    '<td>'+fmt(r.odd_media,2)+'</td>'+
    '<td class="'+pnlClass(r.lucro_medio_entrada)+'">'+money(r.lucro_medio_entrada)+'</td>'+
    '<td class="ns-green">'+fmt(r.maior_good_run,0)+'</td>'+
    '<td class="ns-red">'+fmt(r.maior_bad_run,0)+'</td></tr>').join(""):
    '<tr><td colspan="12">Nenhum jogo atende às condições com o histórico disponível.</td></tr>';
  $("#ns-details").innerHTML="";
  say("Análise concluída: "+response.entradas+" entradas históricas em "+response.resultados.length+
    " campeonato(s). "+(response.sem_classificacao?
      response.sem_classificacao+" partida(s) sem favorito/zebra definido pelas odds foram desconsideradas. ":"")+
    "Expanda uma liga para conferir a classificação e o histórico de cada jogo.");
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
  if(config.condicoes.some(missingConditionValue)){
    say("Informe um número válido apenas nas condições com Valor absoluto.",true);return;
  }
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
    const entries=Object.entries(meta.objetivos);
    const favoriteMarkets=Object.fromEntries(entries.filter(([k])=>
      ["back_favorito","lay_favorito","back_zebra","lay_zebra"].includes(k)));
    const legacyMarkets=Object.fromEntries(entries.filter(([k])=>
      ["back_mandante","lay_mandante","back_visitante","lay_visitante",
       "lay_goleada_mandante","lay_goleada_visitante"].includes(k)));
    const otherMarkets=Object.fromEntries(entries.filter(([k])=>
      !(k in favoriteMarkets)&&!(k in legacyMarkets)));
    $("#ns-objetivo").innerHTML='<optgroup label="Favorito e zebra">'+
      opts(favoriteMarkets,"back_favorito")+'</optgroup>'+
      '<optgroup label="Outros mercados">'+opts(otherMarkets,"back_favorito")+'</optgroup>'+
      '<optgroup label="Estratégias antigas (mando fixo)">'+
      opts(legacyMarkets,"back_favorito")+'</optgroup>';
    $("#ns-league-items").innerHTML=(meta.ligas||[]).map(c=>
      '<label class="ns-league-option"><input type="checkbox" value="'+Number(c.id)+
      '" data-nome="'+esc(c.nome)+'"><span>'+esc(c.nome)+'</span></label>').join("");
    drawLeagues();
    conditionLine();
    await fetchSaved();
    await importLegacy();
    setTab(new URLSearchParams(location.search).get("aba")==="salvas"?"salvas":"simular");
  }catch(e){say(e.message,true);}
}
init();
})();