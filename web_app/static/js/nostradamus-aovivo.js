/* Nostradamus: backtest ao vivo por minuto, com gols reais e odds hipotéticas. */
(()=>{
"use strict";
const $=q=>document.querySelector(q);
const esc=x=>String(x??"").replace(/[&<>"']/g,c=>({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
}[c]));
const n=(value,decimals=0)=>value==null?"—":Number(value).toLocaleString("pt-BR",{
  minimumFractionDigits:decimals,maximumFractionDigits:decimals
});
const brl=v=>v==null?"—":Number(v).toLocaleString("pt-BR",{
  style:"currency",currency:"BRL"
});
const emptyInt=id=>{
  const v=$(id).value.trim();
  return v===""?null:Number(v);
};
const feedback=(text,bad=false)=>{
  $("#ns-inplay-feedback").textContent=text;
  $("#ns-inplay-feedback").classList.toggle("ns-inplay-error",bad);
};
const previous=new Date();
previous.setDate(previous.getDate()-1);
const localDay=[previous.getFullYear(),
  String(previous.getMonth()+1).padStart(2,"0"),
  String(previous.getDate()).padStart(2,"0")].join("-");
$("#ns-inplay-corte").value=localDay;
$("#ns-inplay-corte").max=localDay;
$("#ns-inplay-mercado").disabled=true;

function params(){
  const league=$("#ns-inplay-liga").value;
  return {
    corte:$("#ns-inplay-corte").value,
    campeonato_ids:league?[Number(league)]:[],
    minuto:emptyInt("#ns-inplay-minuto"),
    vencendo:$("#ns-inplay-vencendo").value,
    diferenca_gols:emptyInt("#ns-inplay-diferenca"),
    gols_total:emptyInt("#ns-inplay-total"),
    gols_favorito:emptyInt("#ns-inplay-favorito"),
    gols_zebra:emptyInt("#ns-inplay-zebra"),
    gols_mandante:emptyInt("#ns-inplay-mandante"),
    gols_visitante:emptyInt("#ns-inplay-visitante"),
    mercado:$("#ns-inplay-mercado").value,
    odd_hipotetica:$("#ns-inplay-odd").value.trim()===""?
      null:Number($("#ns-inplay-odd").value)
  };
}
function show(result){
  const overall=result.total;
  $("#ns-inplay-results").hidden=false;
  $("#ns-inplay-kpis").innerHTML=[
    ["Entradas",n(overall.entradas)],
    ["Greens",n(overall.greens)],
    ["Reds",n(overall.reds)],
    ["Win rate",n(overall.win_rate,2)+"%"],
    ["Resultado hipotético",brl(overall.valor_reais)],
    ["Maior good run",n(overall.maior_good_run)],
    ["Maior bad run",n(overall.maior_bad_run)]
  ].map(([label,value])=>
    '<div class="ns-inplay-kpi"><span>'+esc(label)+'</span><strong>'+esc(value)+'</strong></div>'
  ).join("");
  const rows=result.resultados||[];
  $("#ns-inplay-leagues").innerHTML=rows.map(x=>
    "<tr><th>"+esc(x.campeonato)+"</th><td>"+n(x.entradas)+
    "</td><td>"+n(x.greens)+"</td><td>"+n(x.reds)+
    "</td><td>"+n(x.win_rate,2)+"%</td><td>"+brl(x.valor_reais)+
    "</td><td>"+n(x.maior_good_run)+"</td><td>"+n(x.maior_bad_run)+
    "</td></tr>"
  ).join("")||'<tr><td colspan="8">Nenhum jogo corresponde ao cenário informado.</td></tr>';
  const games=result.detalhes||[];
  $("#ns-inplay-games").innerHTML='<table class="ns-table ns-inplay-table">'+
    '<thead><tr><th>Data</th><th>Liga</th><th>Jogo</th>'+
    '<th>Placar na entrada</th><th>Placar final</th><th>Mercado</th>'+
    '<th>Resultado</th><th>Lucro / prejuízo</th></tr></thead><tbody>'+
    games.map(g=>'<tr><td>'+esc(g.data)+'</td><td>'+esc(g.campeonato)+
      '</td><td>'+esc(g.mandante+' × '+g.visitante)+'</td>'+
      '<td>'+esc(g.placar_minuto)+'</td><td>'+esc(g.placar_final)+'</td>'+
      '<td>'+esc(g.mercado)+'</td>'+
      '<td class="'+(g.green?"ns-green":"ns-red")+'">'+
      (g.green?"Green":"Red")+'</td><td>'+brl(g.valor_reais)+
      '</td></tr>').join("")+'</tbody></table>';
  $("#ns-inplay-coverage").textContent=
    "Jogos com gols e placares conferidos até a data de corte: "+
    n(result.jogos_com_placar_auditavel)+". Jogos que satisfizeram os filtros: "+
    n(result.entradas)+". Exibindo até "+n(result.limite_detalhes)+" partidas. "+
    (result.configuracao.odd_hipotetica==null?
      "Não foi informada odd no minuto; não há cálculo financeiro.":"");
  $("#ns-inplay-warning").textContent=result.aviso||"";
  feedback("Simulação concluída: "+n(result.entradas)+
    " entrada(s) no cenário escolhido.");
}
async function initialize(){
  try{
    const r=await fetch("/api/apostas/nostradamus/metadata",{cache:"no-store"});
    if(!r.ok)throw new Error("Falha ao carregar ligas e mercados.");
    const meta=await r.json();
    $("#ns-inplay-liga").innerHTML='<option value="">Todos os campeonatos</option>'+
      (meta.ligas||[]).map(c=>'<option value="'+Number(c.id)+'">'+
        esc(c.nome)+'</option>').join("");
    const options=Object.entries(meta.objetivos||{});
    $("#ns-inplay-mercado").innerHTML=options.map(([key,label])=>
      '<option value="'+esc(key)+'"'+(key==="lay_visitante"?" selected":"")+
      '>'+esc(label)+'</option>').join("");
    $("#ns-inplay-mercado").disabled=false;
  }catch(error){feedback(error.message,true);}
}
$("#ns-inplay-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const config=params();
  const btn=$("#ns-inplay-submit");
  if(btn.disabled)return;
  btn.disabled=true;
  $("#ns-inplay-results").hidden=true;
  feedback("Verificando os gols e o placar de cada jogo no minuto escolhido…");
  try{
    const r=await fetch("/api/apostas/nostradamus/ao-vivo/testar",{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(config)
    });
    const data=await r.json();
    if(!r.ok)throw new Error(typeof data.detail==="string"?data.detail:
      "Não foi possível simular este cenário.");
    show(data);
  }catch(error){feedback(error.message,true);}
  finally{btn.disabled=false;}
});
initialize();
})();
