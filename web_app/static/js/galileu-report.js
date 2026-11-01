/* Galileu: relatório da banca virtual registrada no Supabase. */
(()=>{
"use strict";
const $=s=>document.querySelector(s);
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const num=v=>v==null?"—":Number(v).toLocaleString("pt-BR",{maximumFractionDigits:2});
function summaryData(item){
 return '<tr><td>'+esc(item.nome)+'</td><td>'+num(item.entradas)+'</td>'+
 '<td class="gl-win">'+num(item.greens)+'</td><td class="gl-loss">'+num(item.reds)+'</td>'+
 '<td>'+num(item.pendentes)+'</td><td>'+(item.win_rate==null?"—":num(item.win_rate)+"%")+'</td>'+
 '<td class="'+(item.unidades<0?"gl-loss":"gl-win")+'">'+num(item.unidades)+' u</td></tr>';
}
const empty=colspan=>'<tr><td colspan="'+colspan+'" class="gl-empty-row">Nenhuma entrada registrada.</td></tr>';
async function init(){
try{
 const response=await fetch("/api/apostas/galileu/relatorio");
 const data=await response.json();
 if(!response.ok)throw Error(typeof data.detail==="string"?data.detail:"Erro ao buscar relatório.");
 const r=data.resumo;
 const kpis=[
 ["Banca inicial",data.banca_inicial+" u"],
 ["Banca atual",data.banca_atual+" u"],
 ["Entradas",r.entradas],
 ["Greens",r.greens],
 ["Reds",r.reds],
 ["Pendentes",r.pendentes],
 ["Win rate",r.win_rate==null?"—":num(r.win_rate)+"%"],
 ["Saldo",num(r.unidades)+" u"],
 ];
 $("#gr-kpis").innerHTML=kpis.map(([label,value])=>'<div><span>'+esc(label)+'</span><strong>'+esc(value)+'</strong></div>').join("");
 $("#gr-note").textContent=data.nota;
 $("#gr-leagues").innerHTML=data.por_liga.length?data.por_liga.map(summaryData).join(""):empty(7);
 $("#gr-clubs").innerHTML=data.por_clube.length?data.por_clube.map(summaryData).join(""):empty(7);
 $("#gr-bets").innerHTML=data.entradas.length?data.entradas.map(item=>
 '<tr><td>'+esc(item.data)+'</td><td>'+esc(item.campeonato)+'</td>'+
 '<td>'+esc(item.mandante)+'</td><td>'+esc(item.visitante)+'</td>'+
 '<td>'+esc(item.metodo)+'</td><td>'+esc(item.objetivo_nome)+'</td>'+
 '<td><span class="gl-status gl-'+esc(item.status)+'">'+
 (item.status==="green"?"Green":item.status==="red"?"Red":"Pendente")+
 '</span></td></tr>').join(""):empty(7);
}catch(err){$("#gr-feedback").textContent=err.message;}
}
init();
})();