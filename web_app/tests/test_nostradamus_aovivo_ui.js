/* Contratos de interface e proteção contra odds in-play inventadas. */
const assert=require("node:assert/strict");
const fs=require("node:fs");
const html=fs.readFileSync("templates/nostradamus.html","utf8");
const js=fs.readFileSync("static/js/nostradamus-aovivo.js","utf8");
const base=fs.readFileSync("static/js/nostradamus.js","utf8");
const backend=fs.readFileSync("queries_nostradamus_aovivo.py","utf8");
const app=fs.readFileSync("app.py","utf8");

for(const id of [
  "ns-inplay","ns-inplay-form","ns-inplay-corte","ns-inplay-liga",
  "ns-inplay-minuto","ns-inplay-vencendo","ns-inplay-diferenca",
  "ns-inplay-total","ns-inplay-favorito","ns-inplay-zebra",
  "ns-inplay-mandante","ns-inplay-visitante","ns-inplay-mercado",
  "ns-inplay-odd","ns-inplay-results","ns-inplay-kpis",
  "ns-inplay-leagues","ns-inplay-games","ns-inplay-warning"
]){
  assert.ok(html.includes('id="'+id+'"'),"Falta filtro do cenário: "+id);
}
assert.ok(html.includes('data-ns-tab="ao-vivo"'),"Aba ao vivo deve existir");
assert.ok(html.includes('nostradamus-aovivo.js'),"Script deve ser carregado");
assert.ok(base.includes('$("#ns-inplay").hidden=!inplay;'),"Trocar aba deve mostrar simulador");
assert.ok(js.includes('value="lay_visitante"')||js.includes('key==="lay_visitante"'),
  "Mercado padrão Lay visitante");
assert.ok(html.includes('value="60"'),"Minuto 60 padrão");
assert.ok(html.includes('value="2"'),"Diferença 2 padrão");
assert.ok(js.includes('body:JSON.stringify(config)'),"Simulação deve enviar filtros");
assert.ok(app.includes('/api/apostas/nostradamus/ao-vivo/testar'),"Endpoint deve existir");
assert.ok(backend.includes('g.gols_casa_conferidos=j.gols_casa'),
  "Gols devem corresponder ao placar final oficial");
assert.ok(backend.includes('odd=ns._n(odd)'),"Odd hipotética validada");
assert.ok(backend.includes('ns._units(won,settled_market,c["odd_hipotetica"],0.045)'),
  "Não usar odds pré-jogo no financeiro de minuto");
assert.ok(js.includes('brl(x.valor_reais)'),"Tabela de resultados por liga");
assert.ok(js.includes('g.placar_minuto')&&js.includes('g.placar_final'),
  "Detalhar placar de entrada e final");
console.log("Nostradamus ao vivo: minuto, placar, mercado e odds hipotéticas validados.");
