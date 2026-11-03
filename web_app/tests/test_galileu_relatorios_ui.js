/* Testa os agrupamentos realmente renderizados no Relatórios Galileu. */
"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const html=fs.readFileSync("templates/galileu_financeiro.html","utf8");
const js=fs.readFileSync("static/js/galileu-financeiro.js","utf8");
for(const id of ["gl-report-period","gl-report-by-method","gl-report-by-league","gl-report-by-club"]){
  assert.ok(html.includes('id="'+id+'"'),"A seção deve estar visível: "+id);
}
assert.ok(!html.includes('id="gl-report-breakdown"></div>'),
  "Os agrupamentos não devem ficar escondidos num <details> criado por JS");
assert.ok(html.includes("Resultado por método"),"Faltou título por método");
assert.ok(html.includes("Resultado por liga"),"Faltou título por liga");
assert.ok(html.includes("Resultado por clube"),"Faltou título por clube");
assert.ok(html.includes('galileu-financeiro-v4'),"Invalidar cache do relatório");

const begin=js.indexOf("function groupTable(items,columnName){");
const end=js.indexOf("function render(data){",begin);
assert.ok(begin>=0&&end>begin,"Funções reais de renderização devem existir");
const views={
  "#gl-report-by-method":{innerHTML:""},
  "#gl-report-by-league":{innerHTML:""},
  "#gl-report-by-club":{innerHTML:""},
};
const esc=value=>String(value??"").replace(/&/g,"&amp;").replace(/</g,"&lt;");
const brl=value=>"R$ "+Number(value||0).toFixed(2);
const perc=value=>Number(value||0).toFixed(2)+"%";
const cls=value=>Number(value)>=0?"gl-positive":"gl-negative";
const ctx={
  $:selector=>{assert.ok(selector in views);return views[selector]},
  esc,brl,perc,cls,
};
vm.runInNewContext(
  js.slice(begin,end)+
  'globalThis.runRenderBreakdown=renderBreakdown;',
  ctx
);
function record(nome,pnl){
  return {nome,entradas:2,executadas:1,nao_executadas:1,
    pendentes:0,greens:1,reds:0,win_rate:100,
    stake_executada:20,lucro_prejuizo:pnl,roi:pnl/20*100};
}
const payload={
  agrupamentos:{
    por_metodo:[record("Over 2,5",15),record("Lay visitante",-10)],
    por_liga:[record("Premier League",15)],
    por_clube:[record("Arsenal",15),record("Chelsea",15)],
  },
  resumo_mensal:[{
    mes:"2026-01",
    por_estrategia:[record("Over 2,5",15)],
    por_liga:[record("LaLiga",15)],
    por_clube:[record("Barcelona",15)],
  }],
};
ctx.runRenderBreakdown(payload,"todos");
assert.ok(views["#gl-report-by-method"].innerHTML.includes("Over 2,5"));
assert.ok(views["#gl-report-by-method"].innerHTML.includes("Lay visitante"));
assert.ok(views["#gl-report-by-league"].innerHTML.includes("Premier League"));
assert.ok(views["#gl-report-by-club"].innerHTML.includes("Arsenal"));
assert.ok(views["#gl-report-by-method"].innerHTML.includes("Stake executada"));
assert.ok(views["#gl-report-by-method"].innerHTML.includes("Sem saldo"));
ctx.runRenderBreakdown(payload,"2026-01");
assert.ok(!views["#gl-report-by-method"].innerHTML.includes("Lay visitante"));
assert.ok(views["#gl-report-by-league"].innerHTML.includes("LaLiga"));
assert.ok(views["#gl-report-by-club"].innerHTML.includes("Barcelona"));
ctx.runRenderBreakdown(payload,"2026-02");
assert.ok(views["#gl-report-by-method"].innerHTML.includes("Nenhuma entrada"));
console.log("Relatórios: tabelas de métodos, ligas e clubes renderizadas com filtro e vazios.");
