"use strict";
/* Exercita a função de renderização da tabela mensal, não só snippets. */
const fs=require("node:fs");
const assert=require("node:assert/strict");
const vm=require("node:vm");
const src=fs.readFileSync("static/js/galileu-gameplay.js","utf8");
const html=fs.readFileSync("templates/galileu.html","utf8");
const start=src.indexOf("function selectedMethodsToRemove(){");
const end=src.indexOf("function renderMonth(){",start);
assert.ok(start>=0&&end>start,"Helpers de exibição mensal não encontrados");
for(const header of ["Entradas","Greens","Reds","Win Rate",
                    "Resultado (R$)","Good run máx.","Bad run máx."]){
  assert.ok(src.includes(header),"Falta cabeçalho: "+header);
}
const nodes={
  "#gl-method-performance-table":{innerHTML:""},
  "#gl-method-removal-note":{hidden:false},
};
const state={
  mes_encerrado:"2026-10",
  fechamento_pendente:true,
  metodos_fechamento:[
    {metodo_id:7,nome:"Lay goleada zebra",entradas:8,greens:6,reds:2,
     win_rate:75,lucro_prejuizo:120,maior_good_run:4,maior_bad_run:2},
    {metodo_id:8,nome:"Over 2,5",entradas:0,greens:0,reds:0,
     win_rate:0,lucro_prejuizo:0,maior_good_run:0,maior_bad_run:0},
    {metodo_id:9,nome:"Método antigo",desativado_desde:"2026-10",
     entradas:0,greens:0,reds:0,win_rate:0,lucro_prejuizo:0,
     maior_good_run:0,maior_bad_run:0},
  ],
};
const checked=[{dataset:{removeMethod:"7"}},{dataset:{removeMethod:"8"}}];
const context={
  state,
  document:{querySelectorAll:()=>checked},
  $:id=>nodes[id],
  escapeHTML:v=>String(v).replace(/[&<>"]/g,c=>({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"
  }[c])),
  brl:v=>"R$ "+Number(v).toFixed(2),
  num:(v,d)=>Number(v).toFixed(d),
  color:v=>Number(v)<0?"negative":"positive",
};
vm.runInNewContext(src.slice(start,end)+
  'globalThis.renderMonthTable=renderMethodPerformance;'+
  'globalThis.methodsToRemove=selectedMethodsToRemove;',context);
context.renderMonthTable();
const view=nodes["#gl-method-performance-table"].innerHTML;
assert.ok(view.includes('Lay goleada zebra'));
assert.ok(view.includes('Over 2,5'));
assert.ok(view.includes('Retirar em 2026-11'));
assert.ok(view.includes('Retirado desde 2026-10'));
assert.ok(view.includes('data-remove-method="7"'));
assert.ok(!view.includes('data-remove-method="9"'));
assert.deepEqual(Array.from(context.methodsToRemove()),[7,8]);
assert.equal(nodes["#gl-method-removal-note"].hidden,false);
state.fechamento_pendente=false;
context.renderMonthTable();
assert.ok(!nodes["#gl-method-performance-table"].innerHTML.includes(
  'data-remove-method="7"'),"Depois do fechamento não se pode retirar retroativamente");
assert.equal(nodes["#gl-method-removal-note"].hidden,true);
assert.ok(html.includes('galileu-gameplay-v12'),"Atualizar cache do JS");
console.log("Fechamento mensal: tabela real, zero entradas, bloqueio e seleção aprovados.");
