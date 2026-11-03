/* Testes reais das funções de valores e capacidade, extraídas do frontend. */
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const src=fs.readFileSync("static/js/galileu-gameplay.js","utf8");
const start=src.indexOf("function bulkParseCents(value){");
const end=src.indexOf("function bulkKey(item){",start);
assert.ok(start>=0&&end>start,"Helpers de stake devem existir no frontend");
const ctx={};
vm.runInNewContext(src.slice(start,end),ctx);

const moneyCases=[
  ["20,00",2000],["20.00",2000],["20",2000],
  ["1.000,76",100076],["1,000.76",100076],
  ["R$ 20,00",2000],["0,01",1],
  ["0",null],["-20,00",null],["20,001",null],
  ["abc",null],["1.2.3",null],["",null],
  ["NaN",null],["Infinity",null]
];
for(const [input,expected] of moneyCases){
  assert.equal(ctx.bulkParseCents(input),expected,
    "Conversão em centavos incorreta para "+JSON.stringify(input));
}

// Caso real da captura: saldo R$ 1.009,76 e stake R$ 20,00.
// 50 entradas cabem na banca; 51 ultrapassam o limite.
assert.equal(ctx.bulkMaxAffordable(100976,2000,120),50);
assert.equal(ctx.bulkMaxAffordable(100976,2000,50),50);
assert.equal(ctx.bulkMaxAffordable(100976,2000,40),40);
assert.equal(ctx.bulkMaxAffordable(0,2000,80),0);
assert.equal(ctx.bulkMaxAffordable(100976,null,80),0);
assert.equal(ctx.bulkMaxAffordable(100976,0,80),0);

// Alternativa para incluir 60 métodos: reduzir explicitamente a stake,
// sempre arredondando para baixo para nunca superar a banca.
const allCount=60;
const reducedCents=Math.floor(100976/allCount);
assert.equal(reducedCents,1682);
assert.ok(reducedCents*allCount<=100976);
assert.ok((reducedCents+1)*allCount>100976);
assert.equal(ctx.bulkParseCents((reducedCents/100).toFixed(2)),1682);

console.log("Galileu lote: valores com vírgula, limite de banca e ajuste de stake aprovados.");
