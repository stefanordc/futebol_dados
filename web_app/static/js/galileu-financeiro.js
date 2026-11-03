/* Relatório financeiro de gameplay, somente leitura: cookie HttpOnly do Galileu. */
(()=>{
"use strict";
const $=q=>document.querySelector(q);
const esc=value=>String(value??"").replace(/[&<>"']/g,c=>({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
}[c]));
const brl=value=>Number(value||0).toLocaleString("pt-BR",{style:"currency",currency:"BRL"});
const perc=value=>Number(value||0).toLocaleString("pt-BR",{
  minimumFractionDigits:2,maximumFractionDigits:2})+"%";
const cls=value=>Number(value)>=0?"gl-positive":"gl-negative";
const monthName=month=>month?month.slice(5,7)+"/"+month.slice(0,4):"—";
const dash=value=>value==null?"—":brl(value);
const localTime=value=>{
  if(!value)return "—";
  const dt=new Date(value);
  return Number.isNaN(dt.getTime())?esc(value):dt.toLocaleString("pt-BR");
};
function metricLine(label,value){
  return '<div><span>'+esc(label)+'</span><strong>'+value+'</strong></div>';
}
function groupTable(items,columnName){
  if(!items?.length){
    return '<p class="gl-report-empty">Nenhuma entrada cadastrada neste período.</p>';
  }
  const title=esc(columnName);
  return '<div class="gl-scroll"><table class="gl-table gl-finance-table gl-group-table">'+
    '<thead><tr><th>'+title+'</th><th>Programadas</th><th>Executadas</th>'+
    '<th>Sem saldo</th><th>Pendentes</th><th>Greens</th><th>Reds</th>'+
    '<th>Win Rate</th><th>Stake executada</th><th>L/P (R$)</th><th>ROI</th>'+
    '</tr></thead><tbody>'+
    items.map(r=>'<tr><th scope="row">'+esc(r.nome)+'</th>'+
      '<td>'+Number(r.entradas||0)+'</td>'+
      '<td>'+Number(r.executadas||0)+'</td>'+
      '<td>'+Number(r.nao_executadas||0)+'</td>'+
      '<td>'+Number(r.pendentes||0)+'</td>'+
      '<td>'+Number(r.greens||0)+'</td>'+
      '<td>'+Number(r.reds||0)+'</td>'+
      '<td>'+perc(r.win_rate)+'</td>'+
      '<td>'+brl(r.stake_executada)+'</td>'+
      '<td class="'+cls(r.lucro_prejuizo)+'">'+brl(r.lucro_prejuizo)+'</td>'+
      '<td class="'+cls(r.lucro_prejuizo)+'">'+perc(r.roi)+'</td></tr>').join("")+
    '</tbody></table></div>';
}
function sortKey(value){
  const text=String(value??"").trim();
  const full=text.match(/^(\d{2})\/(\d{2})\/(\d{4})(?:[, ]+(?:às )?(\d{2}):(\d{2}))?/);
  if(full){
    const [,day,month,year,hour="00",minute="00"]=full;
    return {type:"number",value:Number(year+month+day+hour+minute)};
  }
  const monthOnly=text.match(/^(\d{2})\/(\d{4})$/);
  if(monthOnly)return {type:"number",value:Number(monthOnly[2]+monthOnly[1])};
  const raw=text.replace(/[−–]/g,"-").replace(/R\$/g,"").replace(/\s/g,"");
  const ratio=raw.match(/^(\d+)\/(\d+)$/);
  if(ratio)return {type:"number",value:Number(ratio[1])*1000000+Number(ratio[2])};
  if(/^-?\d+(?:\.\d{3})*(?:,\d+)?%?$/.test(raw)){
    return {type:"number",value:Number(raw.replace(/%$/,"").replace(/\./g,"").replace(",","."))};
  }
  return {type:"text",value:text};
}
function compareKeys(a,b){
  if(a.type==="number"&&b.type==="number")return a.value-b.value;
  return String(a.value).localeCompare(String(b.value),"pt-BR",{numeric:true,sensitivity:"base"});
}
function sortTable(header){
  const table=header.closest("table"),body=table?.tBodies?.[0];
  if(!body)return;
  const headers=[...table.tHead.rows[0].cells],index=headers.indexOf(header);
  if(index<0)return;
  const direction=header.getAttribute("aria-sort")==="ascending"?"descending":"ascending";
  const factor=direction==="ascending"?1:-1;
  const rows=[...body.rows].map((row,order)=>({row,order,key:sortKey(row.cells[index]?.textContent)}));
  rows.sort((a,b)=>factor*compareKeys(a.key,b.key)||a.order-b.order);
  body.append(...rows.map(item=>item.row));
  headers.forEach(th=>th.setAttribute("aria-sort",th===header?direction:"none"));
}
function prepareSortableTables(){
  document.querySelectorAll("#gl-report-content table thead th").forEach(th=>{
    th.tabIndex=0;
    th.scope="col";
    th.classList.add("gl-sortable-head");
    th.title="Clique para ordenar crescente / decrescente";
    if(!th.hasAttribute("aria-sort"))th.setAttribute("aria-sort","none");
  });
}
const reportRoot=$("#gl-report-content");
reportRoot.addEventListener("click",event=>{
  const th=event.target.closest("thead th");
  if(th&&reportRoot.contains(th))sortTable(th);
});
reportRoot.addEventListener("keydown",event=>{
  if(event.key!=="Enter"&&event.key!==" ")return;
  const th=event.target.closest("thead th");
  if(!th||!reportRoot.contains(th))return;
  event.preventDefault();
  sortTable(th);
});

function renderBreakdown(data,month){
  const all=data.agrupamentos||{
    por_metodo:[],por_liga:[],por_clube:[]
  };
  const m=(data.resumo_mensal||[]).find(row=>row.mes===month);
  const groups=month==="todos"?all:{
    por_metodo:m?.por_estrategia||[],
    por_liga:m?.por_liga||[],
    por_clube:m?.por_clube||[],
  };
  $("#gl-report-by-method").innerHTML=groupTable(groups.por_metodo,"Método");
  $("#gl-report-by-league").innerHTML=groupTable(groups.por_liga,"Liga");
  $("#gl-report-by-club").innerHTML=groupTable(groups.por_clube,"Clube");
}

function render(data){
  $("#gl-report-content").hidden=false;
  $("#gl-report-summary").innerHTML=[
    ["Banca original",brl(data.banca_original)],
    ["Banca-base mensal",brl(data.banca_base_mes)],
    ["Saldo atual",brl(data.banca_atual)],
    ["Stake padrão",brl(data.stake_padrao)],
    ["L/P apostas",'<span class="'+cls(data.lucro_prejuizo_total)+'">'+
      brl(data.lucro_prejuizo_total)+'</span>'],
    ["ROI total",perc(data.roi_total)],
    ["Entradas não executadas",String((data.resumo_mensal||[]).reduce((n,m)=>n+(m.nao_executadas||0),0))],
    ["Aportes acumulados",brl(data.aporte_total)],
    ["Saques acumulados",brl(data.saque_total)],
  ].map(x=>metricLine(...x)).join("");
  const months=data.resumo_mensal||[];
  $("#gl-report-months").innerHTML=months.length?months.map(m=>
    '<tr><td>'+monthName(m.mes)+'</td><td>'+(m.executadas||0)+' / '+m.entradas+
    '</td><td>'+(m.nao_executadas||0)+'</td><td>'+brl(m.banca_inicio)+'</td>'+
    '<td class="'+cls(m.lucro_prejuizo)+'">'+brl(m.lucro_prejuizo)+'</td>'+
    '<td>'+brl(m.banca_fechamento)+'</td>'+
    '<td>'+brl(m.aporte)+'</td><td>'+brl(m.saque)+'</td>'+
    '<td>'+brl(m.banca_fim)+'</td><td>'+perc(m.roi)+'</td>'+
    '<td>'+(m.fechado?"Fechado":"Em andamento")+'</td></tr>'
  ).join(""):'<tr><td colspan="11">Nenhum período com entradas ou fechamento registrado.</td></tr>';
  const sum=key=>months.reduce((acc,m)=>acc+Number(m[key]||0),0);
  const lastClosed=[...months].filter(m=>m.fechado)
    .sort((a,b)=>String(a.mes).localeCompare(String(b.mes))).at(-1);
  const last=[...months].sort((a,b)=>String(a.mes).localeCompare(String(b.mes))).at(-1);
  const allClosed=months.length>0&&months.every(m=>m.fechado);
  $("#gl-report-months-total").innerHTML=months.length?
    '<tr class="gl-months-total"><th scope="row">TOTAL</th>'+
    '<td>'+sum("executadas")+' / '+sum("entradas")+'</td>'+
    '<td>'+sum("nao_executadas")+'</td><td>—</td>'+
    '<td class="'+cls(sum("lucro_prejuizo"))+'">'+brl(sum("lucro_prejuizo"))+'</td>'+
    '<td title="Último saldo de fechamento">'+
      (lastClosed?brl(lastClosed.banca_fechamento):"—")+'</td>'+
    '<td>'+brl(sum("aporte"))+'</td><td>'+brl(sum("saque"))+'</td>'+
    '<td title="Última banca-base seguinte">'+
      (lastClosed?brl(lastClosed.banca_fim):"—")+'</td>'+
    '<td>'+perc(data.roi_total)+'</td>'+
    '<td>'+(allClosed?"Fechados":last?.fechado?"Parcial":"Em andamento")+
    '</td></tr>':"";
  const labels={
    aporte:"Aporte",saque:"Saque",reajuste_stake:"Reajuste da stake",
    virada_mes:"Atualização da banca-base"
  };
  const management=row=>{
    if(row.gestao_pct_antes==null)return "—";
    return row.stake_fixa_antes!=null?brl(row.stake_fixa_antes)+" fixo":
      perc(row.gestao_pct_antes);
  };
  const nextManagement=row=>{
    if(row.gestao_pct_depois==null)return "—";
    return row.stake_fixa_depois!=null?brl(row.stake_fixa_depois)+" fixo":
      perc(row.gestao_pct_depois);
  };
  $("#gl-report-movements").innerHTML=data.movimentacoes?.length?
    [...data.movimentacoes].reverse().map(r=>
      '<tr><td>'+localTime(r.criado_em)+'</td>'+
      '<td>'+monthName(r.mes)+'</td>'+
      '<td>'+esc(labels[r.tipo]||r.tipo)+'</td>'+
      '<td>'+brl(r.valor)+'</td><td>'+brl(r.banca_antes)+'</td>'+
      '<td>'+brl(r.banca_depois)+'</td>'+
      '<td>'+management(r)+'</td><td>'+nextManagement(r)+'</td></tr>'
    ).join(""):'<tr><td colspan="8">Nenhuma movimentação financeira registrada.</td></tr>';
  const period=$("#gl-report-period");
  period.innerHTML='<option value="todos">Todos os meses</option>'+
    months.map(m=>'<option value="'+esc(m.mes)+'">'+monthName(m.mes)+'</option>')
      .join("");
  period.addEventListener("change",()=>{
    renderBreakdown(data,period.value);
    prepareSortableTables();
  });
  renderBreakdown(data,"todos");
  prepareSortableTables();
}
fetch("/api/apostas/galileu/gameplay/relatorios",{cache:"no-store",credentials:"same-origin"})
  .then(async response=>{
    const data=await response.json();
    if(!response.ok)throw Error(data.detail||"Não foi possível carregar os relatórios.");
    if(!data.iniciado){
      $("#gl-report-message").innerHTML='<p class="gl-alert">Inicie uma gameplay no '+
        '<a href="/apostas/galileu">Galileu</a> para consultar os relatórios.</p>';
      return;
    }
    render(data);
  })
  .catch(error=>{
    $("#gl-report-message").innerHTML='<p class="gl-alert gl-error">'+esc(error.message)+'</p>';
  });
})();
