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
/* Teste real da ordenação: moeda brasileira, negativos, datas e números. */
const sortStart=js.indexOf("function sortKey(value){");
const sortEnd=js.indexOf("const reportRoot=",sortStart);
assert.ok(sortStart>0&&sortEnd>sortStart,"Funções de ordenação ausentes");
const sorter={};
vm.runInNewContext(js.slice(sortStart,sortEnd)+
  "globalThis.sortKeyTest=sortKey;globalThis.sortTableTest=sortTable;",sorter);
assert.equal(sorter.sortKeyTest("R$ 1.270,00").value,1270);
assert.equal(sorter.sortKeyTest("-R$ 155,30").value,-155.3);
assert.ok(sorter.sortKeyTest("01/2025").value<sorter.sortKeyTest("02/2025").value);
assert.ok(sorter.sortKeyTest("02/02/2025, 14:30").value<
  sorter.sortKeyTest("03/02/2025, 11:30").value);
assert.ok(sorter.sortKeyTest("326 / 352").value<
  sorter.sortKeyTest("436 / 452").value);
const cells=(...texts)=>texts.map(textContent=>({textContent}));
const rowA={cells:cells("A","-R$ 155,30")};
const rowB={cells:cells("B","R$ 62,27")};
const rowC={cells:cells("C","-R$ 432,52")};
const body={rows:[rowA,rowB,rowC],append(...rows){this.rows=rows;}};
const table={tBodies:[body],tHead:{rows:[{cells:[]}]}};
const headers=[0,1].map(()=>({
  attrs:{},
  closest:()=>table,
  getAttribute(key){return this.attrs[key]||"none";},
  setAttribute(key,value){this.attrs[key]=value;}
}));
table.tHead.rows[0].cells=headers;
sorter.sortTableTest(headers[1]);
assert.deepEqual(body.rows.map(x=>x.cells[0].textContent),["C","A","B"]);
sorter.sortTableTest(headers[1]);
assert.deepEqual(body.rows.map(x=>x.cells[0].textContent),["B","A","C"]);
assert.equal(headers[1].getAttribute("aria-sort"),"descending");
assert.ok(html.includes('id="gl-report-months-total"'),"Rodapé mensal deve existir");
for(const metric of ['sum("executadas")','sum("entradas")','sum("lucro_prejuizo")',
                     'sum("aporte")','sum("saque")']){
  assert.ok(js.includes(metric),"Rodapé deve contabilizar "+metric);
}
assert.ok(js.includes('lastClosed.banca_fim'),
  "Não somar bancas de meses distintos no rodapé");
assert.ok(js.includes('prepareSortableTables();'),
  "Tabelas criadas ao filtrar meses também devem ser ordenáveis");

console.log("Relatórios: tabelas de métodos, ligas e clubes renderizadas com filtro e vazios.");
