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
function groupTable(items){
  if(!items?.length)return '<p class="gl-note">Nenhuma entrada nesta categoria.</p>';
  return '<div class="gl-scroll"><table class="gl-table gl-finance-table">'+
    '<thead><tr><th>Nome</th><th>Entradas</th><th>Greens</th><th>Reds</th>'+
    '<th>Win Rate</th><th>L/P</th><th>ROI</th></tr></thead><tbody>'+
    items.map(r=>'<tr><td>'+esc(r.nome)+'</td><td>'+r.entradas+'</td>'+
      '<td>'+r.greens+'</td><td>'+r.reds+'</td>'+
      '<td>'+perc(r.win_rate)+'</td>'+
      '<td class="'+cls(r.lucro_prejuizo)+'">'+brl(r.lucro_prejuizo)+'</td>'+
      '<td>'+perc(r.roi)+'</td></tr>').join("")+'</tbody></table></div>';
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
    ["Aportes acumulados",brl(data.aporte_total)],
    ["Saques acumulados",brl(data.saque_total)],
  ].map(x=>metricLine(...x)).join("");
  const months=data.resumo_mensal||[];
  $("#gl-report-months").innerHTML=months.length?months.map(m=>
    '<tr><td>'+monthName(m.mes)+'</td><td>'+brl(m.banca_inicio)+'</td>'+
    '<td class="'+cls(m.lucro_prejuizo)+'">'+brl(m.lucro_prejuizo)+'</td>'+
    '<td>'+brl(m.banca_fechamento)+'</td>'+
    '<td>'+brl(m.aporte)+'</td><td>'+brl(m.saque)+'</td>'+
    '<td>'+brl(m.banca_fim)+'</td><td>'+perc(m.roi)+'</td>'+
    '<td>'+(m.fechado?"Fechado":"Em andamento")+'</td></tr>'
  ).join(""):'<tr><td colspan="9">Nenhum período com entradas ou fechamento registrado.</td></tr>';
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
  $("#gl-report-breakdown").innerHTML=months.length?months.map(m=>
    '<details class="gl-month-detail"><summary><strong>'+
      monthName(m.mes)+'</strong> · '+m.entradas+' entradas · L/P '+
      brl(m.lucro_prejuizo)+' · ROI '+perc(m.roi)+'</summary>'+
      '<div class="gl-finance-subgroups"><details><summary>Por estratégia</summary>'+
      groupTable(m.por_estrategia)+'</details>'+
      '<details><summary>Por liga</summary>'+groupTable(m.por_liga)+'</details>'+
      '<details><summary>Por clube</summary>'+groupTable(m.por_clube)+
      '</details></div></details>').join(""):
      '<p class="gl-note">Ainda não há partidas liquidadas para analisar.</p>';
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
