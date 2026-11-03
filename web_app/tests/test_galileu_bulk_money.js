/* Validação da stake em lotes sem limite de saldo da banca. */
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const src=fs.readFileSync("static/js/galileu-gameplay.js","utf8");
const start=src.indexOf("function bulkParseCents(value){");
const end=src.indexOf("function bulkKey(item){",start);
assert.ok(start>=0&&end>start,"Helper de stake precisa existir");
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
assert.ok(!src.includes("function bulkMaxAffordable("),
  "A confirmação não pode limitar quantidade por banca.");
assert.ok(!src.includes("function bulkAvailableCents("),
  "Não consultar saldo para limitar aposta.");
assert.ok(src.includes("if(!selections.length||!preview.valid)return;"),
  "Validar apenas seleção e stake, não saldo.");
assert.ok(!src.includes("preview.cents>preview.available"),
  "Stake acima da banca não pode bloquear entradas.");
console.log("Galileu: stakes válidas sem limite pelo saldo da banca.");
