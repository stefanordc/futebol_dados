/* Teste de regressão da validação das condições do Nostradamus. */
"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");

const js=fs.readFileSync("static/js/nostradamus.js","utf8");
const css=fs.readFileSync("static/css/nostradamus.css","utf8");
const fragment=js.match(/function missingConditionValue\(condition\)\s*\{[\s\S]*?\n\}/);
assert.ok(fragment,"A validação compartilhada das condições deve existir");
const scope={};
vm.runInNewContext(fragment[0]+";globalThis.validate=missingConditionValue;",scope);
const invalid=scope.validate;

assert.equal(invalid({referencia:"adversario"}),false,
  "Comparação com o adversário não pode exigir valor");
assert.equal(invalid({referencia:"adversario",valor:null}),false,
  "Condição sem valor numérico deve funcionar para adversário");
assert.equal(invalid({referencia:"valor",valor:1.5}),false);
assert.equal(invalid({referencia:"valor",valor:0}),false,"Zero é valor válido");
assert.equal(invalid({referencia:"valor",valor:null}),true);
assert.equal(invalid({referencia:"valor"}),true);
assert.equal(invalid({referencia:"valor",valor:Number.NaN}),true);
assert.equal(invalid({referencia:"visitante",valor:0}),false,
  "Estratégias antigas com ajuste 0 ainda são válidas");
assert.equal(invalid({referencia:"visitante",valor:null}),true,
  "Estratégias antigas com ajuste devem informar valor");

const mixed=[
  {referencia:"adversario"},
  {referencia:"valor",valor:1.7},
  {referencia:"valor",valor:1.5}
];
assert.equal(mixed.some(invalid),false,
  "Conjunto igual ao do print deve passar na simulação");
assert.equal(js.split(".some(missingConditionValue)").length-1,2,
  "Mesma validação usada na simulação e ao salvar");
assert.ok(!js.includes("ns-rule-preview")&&!css.includes("ns-rule-preview"),
  "Não pode renderizar o resumo redundante sob cada condição");
console.log("Validação de backtest e interface sem resumos: OK.");

const html=fs.readFileSync("templates/nostradamus.html","utf8");
const src=fs.readFileSync("static/js/nostradamus.js","utf8");
assert.ok(!html.includes("<th>Entradas cotadas</th>"),"Remover coluna Entradas cotadas");
assert.ok(!html.includes("<th>Resultado (u)</th>"),"Remover coluna Resultado (u)");
assert.ok(!src.includes("fmt(r.cotadas,0)"),"Remover valores de Entradas cotadas");
const summaryRender=src.slice(src.indexOf("function show(response){"),src.indexOf('$("#ns-summary").addEventListener("click"'));
assert.ok(!summaryRender.includes("fmt(r.unidades,2)"),"Remover resultado financeiro da tabela resumo");
assert.ok(src.includes('fmt(r.historico_mandante,0)') && src.includes('fmt(r.historico_visitante,0)'),
  "Detalhamento informa quantos jogos entraram no histórico");
