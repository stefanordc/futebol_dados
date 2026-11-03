/* Galileu — gameplay por rodadas. O navegador nunca recebe placares antes do fechamento. */
(()=>{
"use strict";
const $=q=>document.querySelector(q);
const escapeHTML=x=>String(x??"").replace(/[&<>"']/g,ch=>({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
}[ch]));
const brl=v=>v==null||!Number.isFinite(Number(v))?"—":
  Number(v).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const num=(v,d=1)=>v==null||!Number.isFinite(Number(v))?"—":
  Number(v).toLocaleString("pt-BR",{minimumFractionDigits:d,maximumFractionDigits:d});
const price=x=>x==null?"—":num(x,2);
const color=v=>v==null?"":Number(v)>=0?"gl-positive":"gl-negative";
const dateBR=value=>{
  if(!value)return "—";
  const parts=String(value).slice(0,10).split("-");
  return parts.length===3?parts.reverse().join("/"):String(value);
};
const msg=(value,bad=false)=>{
  $("#gl-message").innerHTML=value?
    '<p class="gl-alert '+(bad?"gl-error":"")+'">'+escapeHTML(value)+'</p>':"";
};
const htmlBtn=(label,cls)=>'<button type="button" class="'+cls+'">'+escapeHTML(label)+'</button>';
const localDate=d=>[d.getFullYear(),String(d.getMonth()+1).padStart(2,"0"),
 String(d.getDate()).padStart(2,"0")].join("-");
let state=null,focusedGame=null,entryGame=null,entryMode=null,detailsTab="method";

async function request(url,options={}){
  const response=await fetch(url,{credentials:"same-origin",cache:"no-store",...options});
  const body=await response.json().catch(()=>({}));
  if(!response.ok)throw Error(typeof body.detail==="string"?body.detail:"Não foi possível concluir a operação.");
  return body;
}
const post=(path,payload={})=>request("/api/apostas/galileu/gameplay/"+path,{
  method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)
});
async function reload(){
  state=await request("/api/apostas/galileu/gameplay/estado");
  render();
}
async function mutate(work){
  msg("");
  try{
    await work();
    await reload();
    return true;
  }catch(e){
    msg(e.message,true);
    return false;
  }
}
const today=new Date();
$("#gl-start-cutoff").max=localDate(new Date(today.getFullYear(),today.getMonth(),today.getDate()-1));
$("#gl-start-cutoff").value=localDate(new Date(today.getFullYear(),today.getMonth(),today.getDate()-180));
function projection(){
  const bank=Number($("#gl-start-bank").value||0);
  const pct=Number($("#gl-start-pct").value||0);
  $("#gl-start-stake").textContent=brl(Math.round(bank*pct)/100);
}
$("#gl-start-bank").addEventListener("input",projection);
$("#gl-start-pct").addEventListener("input",projection);
projection();
$("#gl-setup-form").addEventListener("submit",async e=>{
  e.preventDefault();
  const btn=$("#gl-setup-form button[type=submit]");
  btn.disabled=true;btn.textContent="Iniciando…";
  await mutate(()=>post("iniciar",{
    banca_inicial:$("#gl-start-bank").value,
    gestao_pct:$("#gl-start-pct").value,
    corte:$("#gl-start-cutoff").value
  }));
  btn.disabled=false;btn.textContent="Iniciar gameplay";
});

function methodAlreadyEntered(game,id){
  return (game.entradas||[]).some(entry=>entry.tipo==="metodo"&&
    Number(entry.metodo_id)===Number(id));
}
function availableMethods(game){
  return (game.metodos||[]).filter(m=>!methodAlreadyEntered(game,m.id));
}
function gameRows(g){
  const matched=g.metodos?.length>0;
  const done=state.fase!=="aberta";
  const entries=g.entradas||[];
  return '<article class="gl-game-card '+(matched?"gl-method-match":"")+
    '" data-game-card="'+g.jogo_id+'" tabindex="0" aria-label="Abrir informações: '+
      escapeHTML(g.mandante+' contra '+g.visitante)+'">'+
    '<div class="gl-game-card-main">'+
      '<div class="gl-game-meta">'+dateBR(g.data)+' · '+escapeHTML(g.rodada||"Rodada")+'</div>'+
      '<button type="button" class="gl-game-open" data-details="'+g.jogo_id+'">'+
        '<strong>'+escapeHTML(g.mandante)+' <span>×</span> '+escapeHTML(g.visitante)+'</strong>'+
      '</button>'+
      (matched?'<span class="gl-method-stamp">Método validado</span>':"")+
      '<div class="gl-odds-strip" aria-label="Match Odds">'+
        '<span>1 <strong>'+price(g.odds_match.mandante)+'</strong></span>'+
        '<span>X <strong>'+price(g.odds_match.empate)+'</strong></span>'+
        '<span>2 <strong>'+price(g.odds_match.visitante)+'</strong></span>'+
      '</div>'+
      (entries.length?'<div class="gl-game-entries" aria-label="Entradas confirmadas">'+
        entries.map(entry=>'<div class="gl-game-entry">Programação: '+
          escapeHTML(entry.tipo==="metodo"?(entry.metodo||"Método"):"Manual")+
          ' · '+escapeHTML(entry.mercado)+' · Odd '+price(entry.odd)+
          ' · '+brl(entry.stake)+
          (entry.status==="sem_saldo"?' · Não executada — sem saldo':
            entry.status!=="pendente"?' · <strong class="'+color(entry.lucro_prejuizo)+'">'+
              brl(entry.lucro_prejuizo)+'</strong>':" · Programada")+
          '</div>').join("")+'</div>':"")+
    '</div>'+
    '<div class="gl-game-card-actions">'+
      (done?'<div class="gl-score">'+escapeHTML(String(g.placar?.mandante??"—"))+
        ' × '+escapeHTML(String(g.placar?.visitante??"—"))+'</div>':
        '<span class="gl-hidden-score">Placar oculto</span>')+
      (!done?'<button type="button" class="gl-primary" data-entry="'+g.jogo_id+
        '">Fazer entrada</button>'+
        '<button type="button" class="gl-secondary gl-finish-game" data-finish-game="'+
          g.jogo_id+'">Finalizar jogo</button>':
        entries.length?'<span class="gl-entry-tag">Apuradas</span>':"")+
    '</div></article>';
}

function renderGames(){
  const root=$("#gl-games");
  const games=state.jogos||[];
  // Classificação GLOBAL: nenhum jogo sem método aparece antes dos validados,
  // mesmo que seja de outra liga. Dentro dos grupos, preserva a data.
  const cohorts=[
    {title:"Jogos com método validado",games:games.filter(g=>g.metodos?.length)},
    {title:"Demais jogos",games:games.filter(g=>!g.metodos?.length)}
  ];
  const sections=cohorts.filter(c=>c.games.length).map(cohort=>{
    const groups=new Map();
    [...cohort.games].sort((x,y)=>x.data.localeCompare(y.data)||
       x.campeonato.localeCompare(y.campeonato)||x.jogo_id-y.jogo_id)
       .forEach(g=>{
         const key=g.campeonato+" · "+g.temporada;
         if(!groups.has(key))groups.set(key,[]);
         groups.get(key).push(g);
       });
    return '<section class="gl-priority-group"><h3 class="gl-priority-heading">'+
      escapeHTML(cohort.title)+' <span>'+cohort.games.length+' jogos</span></h3>'+
      [...groups.entries()].map(([league,items])=>
        '<section class="gl-round-league"><h3>'+escapeHTML(league)+
        ' <span>'+items.length+' jogos</span></h3>'+
        '<div class="gl-game-list">'+items.map(gameRows).join("")+'</div></section>'
      ).join("")+'</section>';
  });
  root.innerHTML=sections.length?sections.join(""):'<div class="gl-empty">'+
    (state.rodada_atual.jogos>0?
      "Todos os jogos desta etapa foram finalizados. As entradas continuam registradas. Use Finalizar rodada para apurar os resultados.":
      "Nenhum jogo neste período. Use Avançar período sem jogos para continuar sem revelar placares.")+
    '</div>';
  renderBulkAvailability();
}

function bulkSelections(){
  if(!state||state.fase!=="aberta")return [];
  return (state.jogos||[]).flatMap(game=>
    availableMethods(game).map(method=>({
      jogo_id:game.jogo_id,metodo_id:method.id,
      metodo_versao:method.versao,
      confronto:game.mandante+" × "+game.visitante,
      nome:method.nome,mercado:method.mercado.nome,
      odd:method.mercado.odd
    }))
  ).sort((a,b)=>a.jogo_id-b.jogo_id||a.metodo_id-b.metodo_id);
}
function renderBulkAvailability(){
  const offers=bulkSelections();
  const open=state?.fase==="aberta"&&(state.jogos||[]).length>0;
  $("#gl-bulk-toolbar").hidden=!open;
  $("#gl-bulk-open").disabled=!offers.length;
  $("#gl-bulk-info").textContent=offers.length?
    offers.length+" entrada(s) disponível(is) em "+
      new Set(offers.map(x=>x.jogo_id)).size+" jogo(s), sem repetir métodos.":
    "Todos os métodos validados desta lista já possuem entrada.";
}
/* Helpers puros para fazer a prévia em centavos, sem erro de ponto flutuante.
   Stake pode ser digitada como 20,00 ou 20.00. */
function bulkParseCents(value){
  if(typeof value!=="string"&&typeof value!=="number")return null;
  let raw=String(value).replace(/R\$/gi,"").trim().replace(/\s/g,"");
  if(/^\d{1,3}(?:\.\d{3})+,\d{1,2}$/.test(raw)){
    raw=raw.replace(/\./g,"").replace(",",".");
  }else if(/^\d{1,3}(?:,\d{3})+\.\d{1,2}$/.test(raw)){
    raw=raw.replace(/,/g,"");
  }else if(/^\d+(?:[.,]\d{1,2})?$/.test(raw)){
    raw=raw.replace(",",".");
  }else{
    return null;
  }
  const n=Number(raw);
  const cents=Math.round(n*100);
  return Number.isFinite(n)&&n>0&&Number.isSafeInteger(cents)&&
    Math.abs(n*100-cents)<0.000001?cents:null;
}
function bulkMaxAffordable(availableCents,stakeCents,numberOfOffers){
  if(!Number.isSafeInteger(availableCents)||stakeCents==null||stakeCents<=0||
      !Number.isSafeInteger(numberOfOffers)||numberOfOffers<0)return 0;
  return Math.min(numberOfOffers,Math.floor(Math.max(0,availableCents)/stakeCents));
}
function bulkKey(item){
  return item.jogo_id+":"+item.metodo_id;
}
const bulkSelected=new Set();
let bulkSubmitting=false;
function bulkSelectedOffers(){
  return bulkSelections().filter(offer=>bulkSelected.has(bulkKey(offer)));
}
function bulkAvailableCents(){
  return Math.max(0,Math.round(Number(state?.saldo_disponivel||0)*100));
}
function bulkStakeCents(){
  return bulkParseCents($("#gl-bulk-stake").value);
}
function bulkRenderChecked(){
  $("#gl-bulk-list").querySelectorAll("[data-bulk-key]").forEach(cb=>{
    cb.checked=bulkSelected.has(cb.dataset.bulkKey);
  });
  updateBulkPreview();
}
function updateBulkPreview(){
  const availableOffers=bulkSelections();
  const count=availableOffers.filter(offer=>bulkSelected.has(bulkKey(offer))).length;
  const cents=bulkStakeCents();
  const available=bulkAvailableCents();
  const total=cents===null?null:count*cents;
  const valid=total!==null&&Number.isSafeInteger(total);
  const possible=bulkMaxAffordable(available,cents,availableOffers.length);
  $("#gl-bulk-count").textContent=count+" / "+availableOffers.length;
  $("#gl-bulk-stake-display").textContent=cents!==null?brl(cents/100):"—";
  $("#gl-bulk-total").textContent=valid?brl(total/100):"—";
  let detail="Banca atual de referência: "+brl(available/100)+
    ". As entradas são programadas; não há débito antecipado.";
  if(!valid){
    detail+=" Informe uma stake válida (ex.: 20,00).";
  }else if(total>available){
    detail+=" Exposição planejada acima da banca em "+brl((total-available)/100)+
      ". Você pode confirmar todos os métodos. Na liquidação, entradas sem saldo"+
      " na data do jogo não serão executadas, e não contarão como reds.";
  }else if(count>0){
    detail+=" Exposição planejada de "+brl(total/100)+
      " (a banca não é descontada no momento do agendamento).";
  }
  $("#gl-bulk-balance").textContent=detail;
  $("#gl-bulk-balance").classList.toggle("gl-negative",false);
  const individualRiskOk=cents!==null&&cents<=available;
  if(valid&&!individualRiskOk){
    $("#gl-bulk-balance").textContent+=" A stake individual excede a banca atual; reduza o valor por método.";
  }
  $("#gl-bulk-confirm").disabled=bulkSubmitting||!count||!valid||!individualRiskOk;
  $("#gl-bulk-affordable").disabled=bulkSubmitting||cents===null||!possible;
  $("#gl-bulk-fit-stake").disabled=bulkSubmitting||!availableOffers.length||
    available<availableOffers.length;
  $("#gl-bulk-all").disabled=bulkSubmitting||!availableOffers.length;
  $("#gl-bulk-none").disabled=bulkSubmitting||!count;
  return {count,cents,total,available,valid};
}
$("#gl-bulk-open").addEventListener("click",()=>{
  const offers=bulkSelections();
  if(!offers.length)return;
  bulkSelected.clear();
  offers.forEach(offer=>bulkSelected.add(bulkKey(offer)));
  $("#gl-bulk-stake").value=Number(state.stake_padrao).toFixed(2).replace(".",",");
  $("#gl-bulk-feedback").textContent="";
  $("#gl-bulk-list").innerHTML='<h4>Escolha os métodos que receberão entrada</h4>'+
    '<div class="gl-scroll"><table class="gl-table"><thead><tr>'+
    '<th>Selecionar</th><th>Jogo</th><th>Método</th>'+
    '<th>Mercado</th><th>Odd</th></tr></thead><tbody>'+
    offers.map(offer=>'<tr><td><input type="checkbox" data-bulk-key="'+
      bulkKey(offer)+'" aria-label="Selecionar '+escapeHTML(offer.nome)+
      ' no confronto '+escapeHTML(offer.confronto)+'" checked></td>'+
      '<td>'+escapeHTML(offer.confronto)+'</td>'+
      '<td>'+escapeHTML(offer.nome)+'</td>'+
      '<td>'+escapeHTML(offer.mercado)+'</td>'+
      '<td>'+price(offer.odd)+'</td></tr>').join("")+
    '</tbody></table></div>';
  updateBulkPreview();
  $("#gl-bulk-dialog").showModal();
});
$("#gl-bulk-list").addEventListener("change",event=>{
  const checkbox=event.target.closest("[data-bulk-key]");
  if(!checkbox||bulkSubmitting)return;
  if(checkbox.checked)bulkSelected.add(checkbox.dataset.bulkKey);
  else bulkSelected.delete(checkbox.dataset.bulkKey);
  updateBulkPreview();
});
$("#gl-bulk-stake").addEventListener("input",updateBulkPreview);
$("#gl-bulk-all").addEventListener("click",()=>{
  bulkSelected.clear();
  bulkSelections().forEach(x=>bulkSelected.add(bulkKey(x)));
  bulkRenderChecked();
});
$("#gl-bulk-none").addEventListener("click",()=>{
  bulkSelected.clear();
  bulkRenderChecked();
});
$("#gl-bulk-affordable").addEventListener("click",()=>{
  const offers=bulkSelections();
  const limit=bulkMaxAffordable(bulkAvailableCents(),bulkStakeCents(),offers.length);
  bulkSelected.clear();
  offers.slice(0,limit).forEach(x=>bulkSelected.add(bulkKey(x)));
  bulkRenderChecked();
  $("#gl-bulk-feedback").textContent=limit+" entrada(s) selecionada(s) "+
    "na ordem da prévia, sem ultrapassar o saldo.";
});
$("#gl-bulk-fit-stake").addEventListener("click",()=>{
  const offers=bulkSelections();
  if(!offers.length)return;
  const cents=Math.floor(bulkAvailableCents()/offers.length);
  if(cents<1)return;
  bulkSelected.clear();
  offers.forEach(x=>bulkSelected.add(bulkKey(x)));
  $("#gl-bulk-stake").value=(cents/100).toFixed(2).replace(".",",");
  bulkRenderChecked();
  $("#gl-bulk-feedback").textContent="Stake reduzida para "+
    brl(cents/100)+" por método para incluir todas as "+offers.length+
    " entradas. Confirme somente se concordar com o novo valor.";
});
$("#gl-bulk-form").addEventListener("submit",async event=>{
  event.preventDefault();
  if(bulkSubmitting)return;
  const preview=updateBulkPreview();
  const selections=bulkSelectedOffers();
  if(!selections.length||!preview.valid||preview.cents>preview.available)return;
  bulkSubmitting=true;
  const btn=$("#gl-bulk-confirm");
  btn.disabled=true;
  btn.textContent="Salvando entradas…";
  $("#gl-bulk-feedback").textContent="Gravando entradas no Supabase…";
  msg("");
  try{
    const result=await post("entradas-metodos",{
      stake:(preview.cents/100).toFixed(2),
      versao:state.versao,
      selecoes:selections.map(x=>({
        jogo_id:x.jogo_id,metodo_id:x.metodo_id,metodo_versao:x.metodo_versao
      }))
    });
    const saved=result.entradas||[];
    for(const entry of saved){
      const game=state.jogos.find(g=>g.jogo_id===entry.jogo_id);
      if(game){
        game.entradas=Array.isArray(game.entradas)?game.entradas:[];
        game.entradas.push(entry);
      }
    }
    state.entradas+=saved.length;
    state.exposicao_programada=Number(state.exposicao_programada||0)+
      saved.reduce((sum,x)=>sum+Number(x.stake),0);
    if(result.versao!=null)state.versao=result.versao;
    $("#gl-bank-entries").textContent=num(state.entradas,0);
    $("#gl-bulk-dialog").close();
    renderGames();
    msg(result.mensagem+(result.ignoradas?
      " "+result.ignoradas+" método(s) já registrado(s) ignorado(s).":""));
  }catch(error){
    $("#gl-bulk-feedback").textContent="Não foi possível confirmar: "+error.message;
    msg(error.message,true);
  }finally{
    bulkSubmitting=false;
    btn.textContent="Programar entradas selecionadas";
    updateBulkPreview();
  }
});


function renderRoundResults(){
  const root=$("#gl-round-results");
  const entries=state.resumo_rodada||[];
  const revealed=state.fase==="revelada"||state.fase==="concluida";
  root.hidden=!revealed;
  if(!revealed){root.innerHTML="";return;}
  const total=entries.reduce((acc,x)=>acc+Number(x.lucro_prejuizo||0),0);
  const notExecuted=entries.filter(x=>x.status==="sem_saldo").length;
  root.innerHTML='<h3>Resultado da rodada · '+entries.length+' programada(s)</h3>'+
    '<p class="gl-note">Executadas: '+(entries.length-notExecuted)+
    ' · Não executadas por falta de saldo: '+notExecuted+
    '. Jogos no mesmo dia são tratados como simultâneos; um lucro do dia só pode financiar entradas de datas posteriores. '+
    'Os jogos finalizados individualmente também entram nesta apuração.</p>'+
    (entries.length?
      '<div class="gl-scroll"><table class="gl-table"><thead><tr>'+
      '<th>Confronto</th><th>Placar</th><th>Método</th><th>Mercado</th>'+
      '<th>Odd</th><th>Stake</th><th>Status</th><th>L/P</th></tr></thead><tbody>'+
      entries.map(entry=>'<tr><td>'+escapeHTML(entry.confronto)+'</td>'+
        '<td>'+escapeHTML(entry.placar||"—")+'</td>'+
        '<td>'+escapeHTML(entry.metodo)+'</td>'+
        '<td>'+escapeHTML(entry.mercado)+'</td>'+
        '<td>'+price(entry.odd)+'</td><td>'+brl(entry.stake)+'</td>'+
        '<td>'+escapeHTML(entry.status==="sem_saldo"?"Não executada — sem saldo":
            entry.status==="pendente"?"Programada":entry.status)+'</td>'+
        '<td class="'+color(entry.lucro_prejuizo)+'">'+
          (entry.status==="sem_saldo"?"—":brl(entry.lucro_prejuizo))+'</td>'+
      '</tr>').join("")+'</tbody><tfoot><tr><th colspan="7">TOTAL DA RODADA</th>'+
      '<th class="'+color(total)+'">'+brl(total)+'</th></tr></tfoot></table></div>':
      '<p class="gl-note">Nenhuma entrada foi registrada nesta rodada.</p>');
}

function renderMethodManagement(){
  const methods=state.metodos_catalogo||[];
  const removed=state.metodos_desativados||[];
  const removedIds=new Set(removed.map(item=>Number(item.metodo_id)));
  const available=methods.filter(item=>!removedIds.has(Number(item.id)));
  const select=$("#gl-disable-method-select");
  const previous=select.value;
  select.innerHTML='<option value="">Selecione um método</option>'+
    available.map(item=>'<option value="'+Number(item.id)+'">'+escapeHTML(item.nome)+'</option>').join("");
  if(available.some(item=>String(item.id)===previous))select.value=previous;
  select.disabled=!available.length;
  $("#gl-disable-method-submit").disabled=!available.length;
  $("#gl-disabled-methods").textContent=removed.length?
    "Retirados desta gameplay: "+removed.map(item=>item.nome).join(", ")+
    ". Nenhum deles será marcado em novos jogos.":
    available.length+" método(s) disponível(is) para a gameplay.";
}

$("#gl-disable-method-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const id=Number($("#gl-disable-method-select").value);
  const item=(state.metodos_catalogo||[]).find(m=>Number(m.id)===id);
  if(!id||!item)return;
  if(!window.confirm(
    'Retirar "'+item.nome+'" do Galileu agora?\n\n'+
    "Ele deixará de marcar jogos e não poderá receber novas entradas. "+
    "As entradas pendentes serão canceladas. "+
    "Os resultados já liquidados e o cadastro no Nostradamus serão preservados."
  ))return;
  const button=$("#gl-disable-method-submit");
  button.disabled=true;
  const ok=await mutate(()=>post("retirar-metodo",{metodo_id:id}));
  if(ok)msg('Método "'+item.nome+'" retirado do Galileu. Entradas pendentes canceladas.');
  button.disabled=false;
});

function selectedMethodsToRemove(){
  return [...document.querySelectorAll('#gl-method-performance-table input[data-remove-method]:checked')]
    .map(input=>Number(input.dataset.removeMethod));
}
function renderMethodPerformance(){
  const records=state.metodos_fechamento||[];
  const pending=Boolean(state.fechamento_pendente);
  const nextMonth=state.mes_encerrado?
    (()=>{const [y,m]=state.mes_encerrado.split("-").map(Number);
      const d=new Date(y,m,1);
      return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0");})():"";
  const table=$("#gl-method-performance-table");
  if(!records.length){
    table.innerHTML='<p class="gl-note">Nenhum método cadastrado ou utilizado na gameplay.</p>';
  }else{
    table.innerHTML='<table class="gl-table gl-method-month-table"><thead><tr>'+
      '<th>Método</th><th>Entradas</th><th>Greens</th><th>Reds</th>'+
      '<th>Win Rate</th><th>Resultado (R$)</th>'+
      '<th>Good run máx.</th><th>Bad run máx.</th>'+
      '<th>Próximos meses</th></tr></thead><tbody>'+
      records.map(item=>{
        const methodId=item.metodo_id;
        const previouslyDisabled=Boolean(item.desativado_desde);
        const status=previouslyDisabled?
          '<span class="gl-method-disabled">Retirado desde '+escapeHTML(item.desativado_desde)+'</span>':
          pending&&methodId!=null?
          '<label class="gl-method-removal-option">'+
            '<input type="checkbox" data-remove-method="'+methodId+
            '" aria-label="Retirar '+escapeHTML(item.nome)+' a partir de '+nextMonth+'">'+
            '<span>Retirar em '+escapeHTML(nextMonth)+'</span></label>':
          '<span class="gl-note">Permanece ativo</span>';
        return '<tr><th scope="row">'+escapeHTML(item.nome)+'</th>'+
          '<td>'+num(item.entradas,0)+'</td>'+
          '<td class="gl-positive">'+num(item.greens,0)+'</td>'+
          '<td class="gl-negative">'+num(item.reds,0)+'</td>'+
          '<td>'+num(item.win_rate,1)+'%</td>'+
          '<td class="'+color(item.lucro_prejuizo)+'">'+brl(item.lucro_prejuizo)+'</td>'+
          '<td class="gl-positive">'+num(item.maior_good_run,0)+'</td>'+
          '<td class="gl-negative">'+num(item.maior_bad_run,0)+'</td>'+
          '<td>'+status+'</td></tr>';
      }).join("")+'</tbody></table>';
  }
  $("#gl-method-removal-note").hidden=!pending;
}
function renderMonth(){
  const month=state.mes_encerrado;
  const root=$("#gl-month");
  root.hidden=!month;
  if(!month)return;
  const data=state.resumo_mensal.find(x=>x.mes===month)||{
    banca_fim:state.banca_atual,lucro_prejuizo:0,roi:0,
    entradas:0,greens:0,reds:0,win_rate:0,
    por_estrategia:[],por_liga:[],por_clube:[]
  };
  $("#gl-month-title").textContent="Resumo de "+month.slice(5)+"/"+month.slice(0,4);
  const fields=[
    ["Banca-base do mês",brl(data.banca_inicio)],
    ["Saldo após apostas",brl(data.banca_fechamento)],
    ["Lucro / Prejuízo",brl(data.lucro_prejuizo)],
    ["ROI",num(data.roi,2)+"%"],
    ["Programadas",num(data.entradas,0)],
    ["Executadas",num(data.executadas||0,0)],
    ["Não executadas",num(data.nao_executadas||0,0)],
    ["Greens / Reds",data.greens+" / "+data.reds],
    ["Win Rate",num(data.win_rate,1)+"%"],
  ];
  $("#gl-month-kpis").innerHTML=fields.map(([label,value])=>
    '<div><span>'+label+'</span><strong>'+value+'</strong></div>').join("");
  renderMethodPerformance();
  $("#gl-month-groups").innerHTML=[
    ["Por estratégias",data.por_estrategia],
    ["Por ligas",data.por_liga],
    ["Por clubes",data.por_clube],
  ].map(([label,rows])=>'<details class="gl-month-detail"><summary>'+
     escapeHTML(label)+'</summary>'+tableRows(rows)+'</details>').join("")+
     '<p class="gl-note">Na visão por clubes, a mesma entrada é atribuída aos dois participantes; os totais por clube não devem ser somados.</p>';
  $("#gl-close-form").hidden=!state.fechamento_pendente;
  $("#gl-month-confirmed").hidden=!state.fechamento_realizado;
  if(state.fechamento_pendente)updateClosePreview();
}
function updateClosePreview(){
  if(!state?.fechamento_pendente)return;
  const deposits=$("#gl-close-deposit-choice").value;
  const withdrawals=$("#gl-close-withdraw-choice").value;
  const adjustment=$("#gl-close-stake-choice").value;
  const depositOn=deposits==="sim",withdrawOn=withdrawals==="sim",changeOn=adjustment==="sim";
  $("#gl-close-deposit-wrap").hidden=!depositOn;
  $("#gl-close-withdraw-wrap").hidden=!withdrawOn;
  $("#gl-close-stake-wrap").hidden=!changeOn;
  const deposit=depositOn?Number($("#gl-close-deposit").value):0;
  const withdrawal=withdrawOn?Number($("#gl-close-withdraw").value):0;
  const closing=Number(state.banca_atual);
  const next=closing+deposit-withdrawal;
  const method=changeOn?$("#gl-close-stake-type").value:
    state.stake_fixa!=null?"fixo":"percentual";
  const changeValue=changeOn?Number($("#gl-close-stake-value").value):
    (method==="fixo"?Number(state.stake_fixa):Number(state.gestao_pct));
  const nextStake=method==="fixo"?changeValue:Math.round(next*changeValue)/100;
  const allSelected=[deposits,withdrawals,adjustment].every(x=>x==="sim"||x==="nao");
  const invalid=!allSelected||!Number.isFinite(next)||next<0||
    (depositOn&&(!Number.isFinite(deposit)||deposit<=0))||
    (withdrawOn&&(!Number.isFinite(withdrawal)||withdrawal<=0))||
    (changeOn&&(!Number.isFinite(changeValue)||changeValue<=0))||
    (method==="percentual"&&changeValue>100)||
    (method==="fixo"&&changeValue>next);
  $("#gl-close-bank-before").textContent=brl(closing);
  $("#gl-close-bank-after").textContent=brl(next);
  $("#gl-close-stake-after").textContent=brl(nextStake);
  $("#gl-close-info").textContent=!allSelected?
    "Responda Sim ou Não às três perguntas para registrar o fechamento.":
    invalid?"Confira os valores: saque não pode exceder o saldo com aportes e a stake deve ser válida.":
    "Aporte e saque não entram no lucro/ROI. A nova banca-base ficará fixa durante o próximo mês.";
  $("#gl-close-submit").disabled=invalid;
}
["gl-close-deposit-choice","gl-close-withdraw-choice","gl-close-stake-choice",
 "gl-close-deposit","gl-close-withdraw","gl-close-stake-type","gl-close-stake-value"]
.forEach(id=>document.getElementById(id).addEventListener("input",updateClosePreview));
$("#gl-close-form").addEventListener("submit",async event=>{
  event.preventDefault();
  updateClosePreview();
  const btn=$("#gl-close-submit");
  if(btn.disabled)return;
  const deposit=$("#gl-close-deposit-choice").value==="sim";
  const withdrawal=$("#gl-close-withdraw-choice").value==="sim";
  const adjust=$("#gl-close-stake-choice").value==="sim";
  const payload={
    fazer_aporte:deposit,
    fazer_saque:withdrawal,
    alterar_stake:adjust,
    aporte:deposit?$("#gl-close-deposit").value:null,
    saque:withdrawal?$("#gl-close-withdraw").value:null,
    tipo_stake:adjust?$("#gl-close-stake-type").value:null,
    valor_stake:adjust?$("#gl-close-stake-value").value:null,
    retirar_metodos:selectedMethodsToRemove(),
  };
  const toDisable=payload.retirar_metodos.map(mid=>
    (state.metodos_fechamento||[]).find(m=>m.metodo_id===mid)?.nome||"Método "+mid);
  if(!window.confirm(
    "Confirmar o fechamento de "+state.mes_encerrado+
    " e definir "+$("#gl-close-bank-after").textContent+
    " como banca-base do próximo mês?"+
    (toDisable.length?"\n\nMétodos retirados a partir do próximo mês:\n- "+
      toDisable.join("\n- "):"\n\nTodos os métodos ativos continuarão disponíveis.")+
    "\n\nO histórico de entradas e os métodos no Nostradamus serão preservados."
  ))return;
  btn.disabled=true;
  btn.textContent="Registrando fechamento…";
  await mutate(()=>post("fechar-mes",payload));
  btn.textContent="Confirmar fechamento do mês";
});

function renderHistory(){
  const items=state.resumo_mensal||[];
  $("#gl-month-history").hidden=!items.length;
  $("#gl-history-content").innerHTML=items.map(m=>
    '<details class="gl-month-detail"><summary>'+escapeHTML(m.mes)+
    ' · '+brl(m.lucro_prejuizo)+' · '+num(m.roi,1)+'% ROI</summary>'+
    '<div class="gl-month-history-stats">Banca: '+brl(m.banca_fim)+
      ' · '+m.entradas+' programadas · '+(m.executadas||0)+' executadas · '+
      (m.nao_executadas||0)+' sem saldo · '+m.greens+' greens · '+m.reds+
      ' reds · '+num(m.win_rate,1)+'% win rate</div></details>').join("");
}
function render(){
  const started=Boolean(state?.iniciado);
  $("#gl-setup").hidden=started;
  $("#gl-gameplay").hidden=!started;
  if(!started)return;
  $("#gl-bank-initial").textContent=brl(state.banca_base_mes);
  $("#gl-bank-original").textContent="Banca original: "+brl(state.banca_inicial);
  $("#gl-bank-current").textContent=brl(state.banca_atual);
  $("#gl-bank-stake").textContent=brl(state.stake_padrao);
  $("#gl-bank-percent").textContent=state.stake_fixa==null?
    num(state.gestao_pct,2)+"% da banca-base do mês":"Stake fixa";
  $("#gl-bank-entries").textContent=num(state.entradas,0);
  $("#gl-round-title").textContent="Rodada "+state.rodada_indice;
  // O intervalo exibido é sempre de até 10 dias e nunca cruza o mês.
  // Data de corte atual é a última data de jogos da etapa anterior.
  const start=state.corte_atual?
    localDate(new Date(state.corte_atual+"T12:00:00")):
    null;
  const first=start?localDate(new Date(
    Number(start.slice(0,4)),Number(start.slice(5,7))-1,
    Number(start.slice(8,10))+1)):null;
  $("#gl-round-dates").textContent=state.limite_janela?
    dateBR(first)+" até "+dateBR(state.limite_janela):"Sem próximos jogos";
  $("#gl-round-cutoff").textContent="Data de corte atual: "+dateBR(state.corte_atual)+
    " · Jogos exibidos até "+dateBR(state.limite_janela)+
    " (máximo de 10 dias e até o fim do mês).";
  const open=state.fase==="aberta";
  $("#gl-finish").hidden=!open||!state.rodada_atual.jogos;
  $("#gl-next").hidden=!(state.fase==="revelada"||state.pode_pular_vazio);
  $("#gl-next").disabled=Boolean(state.fechamento_pendente);
  $("#gl-next").textContent=state.fechamento_pendente?
    "Conclua o fechamento mensal para avançar":state.pode_pular_vazio?
    "Avançar período sem jogos":
    state.pode_avancar?"Próxima rodada":"Concluir gameplay";
  $("#gl-round-status").textContent=state.pode_pular_vazio?
    "Não há jogos neste intervalo. Você pode avançar sem fazer entradas.":
    open?"Selecione suas entradas e finalize quando os jogos tiverem resultados disponíveis.":
    state.fase==="revelada"?"Rodada finalizada. Placar e resultado das entradas revelados.":
    "Todas as rodadas cadastradas foram percorridas.";
  $("#gl-games-closed").textContent=state.jogos_finalizados?
    state.jogos_finalizados+" jogo(s) finalizado(s) e removido(s) desta rodada. Entradas preservadas.":"";
  $("#gl-round-help").textContent=state.pode_pular_vazio?
    "Sem jogos nesta janela. Avance para o próximo período, sem alterar a banca.":
    open?"Clique no jogo para analisar. Métodos primeiro; placares permanecem ocultos.":
    "Rodada encerrada. Consulte os placares e seus resultados virtuais.";
  renderMethodManagement();renderGames();renderRoundResults();renderMonth();renderHistory();
}

const getGame=id=>state?.jogos?.find(g=>g.jogo_id===Number(id));
function statsHTML(game){
  const home=game.estatisticas.mandante;
  const away=game.estatisticas.visitante;
  if(!home||!away)return '<p class="gl-note">Histórico insuficiente: são necessários cinco jogos anteriores de cada clube, na mesma competição e temporada.</p>';
  const names={
    pontos_jogo:"Pontos por jogo",aproveitamento:"Aproveitamento (%)",
    gols_feitos:"Gols marcados por jogo",gols_sofridos:"Gols sofridos por jogo",
    xg:"xG",xgot:"xGOT",chutes:"Finalizações",chutes_certos:"Finalizações certas",
    escanteios:"Escanteios",posse:"Posse (%)",grandes_chances:"Grandes chances",
    km:"Km percorridos",sprints:"Sprints",vitorias_pct:"Vitórias (%)"
  };
  return '<p class="gl-note">Histórico anterior: '+game.amostra.mandante+
    ' jogos de '+escapeHTML(game.mandante)+' e '+game.amostra.visitante+
    ' jogos de '+escapeHTML(game.visitante)+'.</p>'+
    '<div class="gl-scroll"><table class="gl-table"><thead><tr><th>Indicador</th>'+
    '<th>'+escapeHTML(game.mandante)+'</th><th>'+escapeHTML(game.visitante)+
    '</th></tr></thead><tbody>'+
    Object.entries(names).map(([key,label])=>
      '<tr><td>'+escapeHTML(label)+'</td><td>'+num(home[key],2)+'</td>'+
      '<td>'+num(away[key],2)+'</td></tr>').join("")+'</tbody></table></div>';
}
function ruleHTML(rule){
  if(rule.tipo==="odd")return '<li><strong>'+escapeHTML(rule.nome)+'</strong>: odd '+
    price(rule.odd)+(rule.odd_min!=null?" · mín. "+price(rule.odd_min):"")+
    (rule.odd_max!=null?" · máx. "+price(rule.odd_max):"")+'</li>';
  const side=rule.lado==="ambos"?"Ambos":rule.lado==="favorito"?"Favorito":
    rule.lado==="zebra"?"Zebra":rule.lado==="mandante"?"Mandante":"Visitante";
  const actual=rule.lado==="ambos"?
    "Mandante "+num(rule.observado_mandante,2)+
    " / Visitante "+num(rule.observado_visitante,2):num(rule.observado,2);
  return '<li><strong>'+escapeHTML(side)+' · '+escapeHTML(rule.nome)+
    '</strong> · '+actual+' '+escapeHTML(rule.comparador)+' '+
    num(rule.comparado,2)+'</li>';
}
function methodsHTML(game){
  if(!game.metodos.length)return '<p class="gl-note">Nenhum método salvo passou em todas as condições para este confronto.</p>';
  const closed=state.fase!=="aberta";
  return game.metodos.map(m=>{
    const used=methodAlreadyEntered(game,m.id);
    return '<section class="gl-validated-method"><span class="gl-method-stamp">Método validado</span>'+
      '<h4>'+escapeHTML(m.nome)+'</h4>'+
      '<p>Mercado: '+escapeHTML(m.mercado.nome)+' · Odd '+price(m.mercado.odd)+
      (m.mercado.estimada?" (Lay estimado)":"")+'</p>'+
      '<ol class="gl-method-rules">'+m.regras.map(ruleHTML).join("")+'</ol>'+
      '<button type="button" class="gl-primary gl-method-action" data-method-entry="'+m.id+
      '" '+(closed||used?'disabled':'')+'>'+
      (used?"Entrada já realizada":closed?"Rodada encerrada":"Fazer entrada neste método")+
      '</button></section>';
  }).join("");
}

function showDetails(game){
  focusedGame=game;
  detailsTab=game.metodos.length?"method":"stats";
  $("#gl-details-title").textContent=game.mandante+" × "+game.visitante;
  drawDetails();
  $("#gl-details-dialog").showModal();
}
function drawDetails(){
  const g=focusedGame;
  $("#gl-details-content").innerHTML=
   '<div class="gl-detail-tabs" role="tablist" aria-label="Detalhes do jogo">'+
     (g.metodos.length?'<button type="button" data-detail-tab="method" '+
       'class="'+(detailsTab==="method"?"is-active":"")+'">Métodos e regras</button>':"")+
     '<button type="button" data-detail-tab="stats" class="'+
       (detailsTab==="stats"?"is-active":"")+'">Estatísticas dos clubes</button></div>'+
   '<div class="gl-detail-body">'+(detailsTab==="method"?methodsHTML(g):statsHTML(g))+'</div>';
}
$("#gl-details-content").addEventListener("click",event=>{
  const action=event.target.closest("[data-method-entry]");
  if(action){
    const method=focusedGame?.metodos.find(m=>String(m.id)===action.dataset.methodEntry);
    if(method&&!methodAlreadyEntered(focusedGame,method.id)){
      const game=focusedGame;
      $("#gl-details-dialog").close();
      showEntry(game,method.id);
    }
    return;
  }
  const btn=event.target.closest("[data-detail-tab]");
  if(!btn)return;
  detailsTab=btn.dataset.detailTab;
  drawDetails();
});
$("#gl-games").addEventListener("click",async e=>{
  const entry=e.target.closest("[data-entry]");
  if(entry){
    const g=getGame(entry.dataset.entry);
    if(g)showEntry(g);
    return;
  }
  const finish=e.target.closest("[data-finish-game]");
  if(finish){
    const g=getGame(finish.dataset.finishGame);
    if(!g)return;
    if(!window.confirm("Finalizar "+g.mandante+" × "+g.visitante+
      "? O jogo será removido da lista e novas entradas não serão aceitas. "+
      "As entradas já confirmadas serão apuradas ao finalizar a rodada."))return;
    finish.disabled=true;
    await mutate(()=>post("finalizar-jogo",{jogo_id:g.jogo_id}));
    return;
  }
  const card=e.target.closest("[data-game-card]");
  if(card){
    const g=getGame(card.dataset.gameCard);
    if(g)showDetails(g);
  }
});
$("#gl-games").addEventListener("keydown",event=>{
  if(event.target.matches("[data-game-card]")&&
    (event.key==="Enter"||event.key===" ")){
    event.preventDefault();
    const g=getGame(event.target.dataset.gameCard);
    if(g)showDetails(g);
  }
});
document.querySelectorAll("[data-close]").forEach(button=>button.addEventListener("click",()=>{
  document.getElementById(button.dataset.close)?.close();
}));
function showEntry(game,methodId=null){
  entryGame=game;
  entryMode=null;
  const available=availableMethods(game);
  $("#gl-entry-title").textContent="Fazer entrada · "+game.mandante+" × "+game.visitante;
  $("#gl-entry-choice").hidden=methodId!==null||!available.length;
  $("#gl-entry-form").hidden=methodId===null&&Boolean(available.length);
  $("#gl-entry-stake").value=Number(state.stake_padrao).toFixed(2);
  if(methodId!==null){
    selectEntryMode("metodo",methodId);
  }else if(!available.length){
    selectEntryMode("manual");
  }
  $("#gl-entry-dialog").showModal();
}
function selectEntryMode(mode,methodId=null){
  entryMode=mode;
  $("#gl-entry-choice").hidden=true;
  $("#gl-entry-form").hidden=false;
  const isMethod=mode==="metodo";
  $("#gl-entry-method-wrap").hidden=!isMethod;
  $("#gl-entry-market-wrap").hidden=isMethod;
  if(isMethod){
    $("#gl-entry-method").innerHTML=availableMethods(entryGame).map(m=>
      '<option value="'+m.id+'">'+escapeHTML(m.nome)+" · "+
      escapeHTML(m.mercado.nome)+'</option>').join("");
    if(methodId!==null)$("#gl-entry-method").value=String(methodId);
  }else{
    $("#gl-entry-market").innerHTML=entryGame.mercados.map(m=>
      '<option value="'+escapeHTML(m.mercado)+'">'+escapeHTML(m.nome)+
      ' · '+price(m.odd)+(m.estimada?" (estimado)":"")+'</option>').join("");
  }
  updateEntryPrice();
}
function updateEntryPrice(){
  if(!entryMode||!entryGame)return;
  const offer=entryMode==="metodo"?
    availableMethods(entryGame).find(m=>String(m.id)===$("#gl-entry-method").value)?.mercado:
    entryGame.mercados.find(m=>m.mercado===$("#gl-entry-market").value);
  $("#gl-entry-odd").textContent=price(offer?.odd);
  $("#gl-entry-odd-source").textContent=offer?.estimada?
    "Lay estimado, não executável":"Odd histórica importada";
  $("#gl-entry-confirm").disabled=!offer;
}
$("#gl-entry-method-button").addEventListener("click",()=>selectEntryMode("metodo"));
$("#gl-entry-manual-button").addEventListener("click",()=>selectEntryMode("manual"));
$("#gl-entry-method").addEventListener("change",updateEntryPrice);
$("#gl-entry-market").addEventListener("change",updateEntryPrice);
$("#gl-entry-cancel").addEventListener("click",()=>$("#gl-entry-dialog").close());
$("#gl-entry-form").addEventListener("submit",async e=>{
  e.preventDefault();
  const stake=$("#gl-entry-stake").value;
  const market=entryMode==="metodo"?
    availableMethods(entryGame).find(m=>String(m.id)===$("#gl-entry-method").value)?.mercado:
    entryGame.mercados.find(m=>m.mercado===$("#gl-entry-market").value);
  if(!market){msg("Selecione um mercado com odd disponível.",true);return;}
  if(!window.confirm("Confirmar entrada virtual de "+brl(stake)+
      " no mercado "+market.nome+" à odd "+price(market.odd)+"?"))return;
  const data={jogo_id:entryGame.jogo_id,tipo:entryMode,stake};
  if(entryMode==="metodo"){
    const m=availableMethods(entryGame).find(m=>String(m.id)===$("#gl-entry-method").value);
    if(!m){msg("Este método já recebeu uma entrada neste jogo.",true);return;}
    data.metodo_id=m.id;data.metodo_versao=m.versao;
  }else{
    data.mercado=market.mercado;
  }
  const btn=$("#gl-entry-confirm");
  btn.disabled=true;
  btn.textContent="Gravando entrada…";
  msg("");
  try{
    // O servidor devolve a entrada depois do COMMIT. Atualizamos o estado
    // desta partida sem recarregar as estatísticas de todas as ligas.
    const result=await post("entrada",data);
    const game=state?.jogos?.find(g=>g.jogo_id===data.jogo_id);
    if(game&&result.entrada){
      game.entradas=Array.isArray(game.entradas)?game.entradas:[];
      game.entradas.push(result.entrada);
      state.entradas+=1;
      state.exposicao_programada=Number(state.exposicao_programada||0)+
        Number(result.entrada.stake);
      if(result.versao!=null)state.versao=result.versao;
      $("#gl-bank-entries").textContent=num(state.entradas,0);
      renderGames();
    }else{
      // Compatibilidade com versões antigas ou atualização em outra aba.
      await reload();
    }
    $("#gl-entry-dialog").close();
    msg(result.mensagem||"Entrada confirmada e salva.");
  }catch(error){
    msg(error.message,true);
  }finally{
    btn.disabled=false;
    btn.textContent="Confirmar entrada";
  }
});

$("#gl-finish").addEventListener("click",async()=>{
  if(!window.confirm("Finalizar a rodada e revelar todos os placares disponíveis? Depois não será possível incluir novas entradas nesta rodada."))return;
  const btn=$("#gl-finish");btn.disabled=true;
  await mutate(()=>post("finalizar"));
  btn.disabled=false;
});
$("#gl-next").addEventListener("click",async()=>{
  const btn=$("#gl-next");btn.disabled=true;
  await mutate(()=>post("proxima"));
  btn.disabled=false;
});
$("#gl-restart").addEventListener("click",async()=>{
  const reply=window.prompt("Esta ação apaga TODAS as entradas e o progresso da gameplay. Digite REINICIAR para confirmar:");
  if(reply!=="REINICIAR")return;
  await mutate(()=>request("/api/apostas/galileu/gameplay/reiniciar",{method:"DELETE"}));
});
reload().catch(err=>msg(err.message,true));
})();
