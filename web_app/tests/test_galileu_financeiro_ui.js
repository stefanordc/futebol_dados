const fs=require("node:fs");
const assert=require("node:assert/strict");
const page=fs.readFileSync("templates/galileu_financeiro.html","utf8");
const js=fs.readFileSync("static/js/galileu-financeiro.js","utf8");
const back=fs.readFileSync("queries_galileu_gameplay.py","utf8");
for(const id of [
  "gl-report-message","gl-report-content","gl-report-summary",
  "gl-report-months","gl-report-movements","gl-report-breakdown"
])assert.ok(page.includes('id="'+id+'"'),"Faltou "+id);
assert.ok(page.includes('href="/apostas/galileu"'),"Retorno à gameplay");
assert.ok(page.includes('galileu-financeiro.js'),"Página precisa do renderizador financeiro");
assert.ok(js.includes('credentials:"same-origin"'),"Autorização por cookie privado");
assert.ok(js.includes('gameplay/relatorios'),"Consulta endpoint financeiro");
assert.ok(js.includes('m.banca_inicio'),"Mostrar saldo base anterior");
assert.ok(js.includes('m.banca_fechamento'),"Mostrar saldo após apostas");
assert.ok(js.includes('m.aporte'),"Mostrar aportes");
assert.ok(js.includes('m.saque'),"Mostrar saques");
assert.ok(js.includes('m.banca_fim'),"Mostrar banca-base seguinte");
assert.ok(js.includes('data.movimentacoes'),"Mostrar extrato auditável");
assert.ok(js.includes('m.por_estrategia'),"Relatório por estratégia");
assert.ok(js.includes('m.por_liga'),"Relatório por liga");
assert.ok(js.includes('m.por_clube'),"Relatório por clube");
assert.ok(back.includes('profit/exposure*100'),"ROI exclui fluxo de caixa");
assert.ok(!js.includes("placar"),"Relatório financeiro não apresenta placares de partidas");
console.log("Relatórios da banca: estrutura, métricas e auditabilidade verificados.");
