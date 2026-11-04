/* Aba ao vivo: editor compartilhado, múltiplas ligas, IA e resultados financeiros. */
const assert=require("node:assert/strict");
const fs=require("node:fs");
const html=fs.readFileSync("templates/nostradamus.html","utf8");
const js=fs.readFileSync("static/js/nostradamus-aovivo.js","utf8");
const base=fs.readFileSync("static/js/nostradamus.js","utf8");
const backend=fs.readFileSync("queries_nostradamus_aovivo.py","utf8");
const app=fs.readFileSync("app.py","utf8");

for(const id of [
  "ns-inplay","ns-inplay-form","ns-inplay-corte","ns-inplay-janela",
  "ns-inplay-league-trigger","ns-inplay-league-summary",
  "ns-inplay-league-options","ns-inplay-league-items",
  "ns-inplay-league-all","ns-inplay-league-select-all",
  "ns-inplay-minuto","ns-inplay-vencendo","ns-inplay-diferenca",
  "ns-inplay-total","ns-inplay-favorito","ns-inplay-zebra",
  "ns-inplay-mandante","ns-inplay-visitante","ns-inplay-mercado",
  "ns-inplay-odd","ns-inplay-conditions","ns-inplay-count","ns-inplay-add",
  "ns-inplay-results","ns-inplay-kpis","ns-inplay-leagues",
  "ns-inplay-total","ns-inplay-games","ns-inplay-warning",
  "ns-inplay-ai-run","ns-inplay-ai-output","ns-inplay-ai-undo",
  "ns-inplay-ai-test-shortcut"
]){
  assert.ok(html.includes('id="'+id+'"'),"Campo/controle ausente: "+id);
}
for(const role of ["mandante","visitante","favorito","zebra"]){
  for(const suffix of ["min","max"]){
    assert.ok(html.includes('id="ns-inplay-'+role+'-'+suffix+'"'),
      "Falta faixa de gols: "+role+" "+suffix);
    assert.ok(js.includes('"gols_"+role+"_'+suffix+'"')||js.includes('"gols_"+role+"_min"')||js.includes('goals["gols_"+role+"_'),
      "Faixa deve ser enviada no payload");
  }
}
assert.ok(html.includes('data-ns-tab="ao-vivo"'),"Aba de backtest ao vivo");
assert.ok(html.includes('nostradamus-aovivo.js'),"Script da aba ao vivo");
assert.ok(base.includes('$("#ns-inplay").hidden=!inplay;'),"Troca de aba");
assert.ok(base.includes("window.NostradamusRuleBuilder"),"Editor de condições compartilhado");
assert.ok(base.includes('indicatorOpts(meta.metricas,meta.mercados_odd,'),
  "Editor deve aceitar indicadores, dados físicos e odds");
assert.ok(js.includes('rules.add("#ns-inplay-conditions"'),
  "Mesma construção de até 10 regras da aba principal");
assert.ok(js.includes('if($("#ns-inplay-conditions").children.length>=10)'),
  "Limite de 10 regras");
assert.ok(html.includes('value="60"'),"Minuto padrão 60");
assert.ok(html.includes('value="2"'),"Diferença padrão 2");
assert.ok(html.includes('value="2.00"'),"Odd 2,00 explicitamente hipotética");
assert.ok(html.includes('somente ilustrativa'),"Não apresentar odds como cotações reais");
assert.ok(js.includes('input type="checkbox" checked'),"Ligas selecionadas por padrão");
assert.ok(js.includes('campeonato_ids:selectedLeagues()'),"Filtro permite múltiplas ligas");
assert.ok(js.includes('body:JSON.stringify(config)'),"Requisição validada");
assert.ok(app.includes('/api/apostas/nostradamus/ao-vivo/testar'),"Endpoint de simulação");
assert.ok(app.includes('/api/apostas/nostradamus/ao-vivo/otimizar'),"Endpoint da IA");
assert.ok(backend.includes('g.gols_casa_conferidos=j.gols_casa'),
  "Verificar eventos de gols frente ao placar oficial");
assert.ok(backend.includes('ns.RAW.format(competition=predicate)'),
  "Condições pré-jogo utilizam mesmo histórico cronológico da aba principal");
assert.ok(backend.includes('ns._evaluate_condition('),"Reutilizar validação de condição");
assert.ok(backend.includes('ns._history_item('),"Histórico de partidas anteriores");
assert.ok(backend.includes('odd=c["odd_hipotetica"]'),
  "Não usar odds pré-jogo como preço real do minuto 60");
assert.ok(js.includes('money(x.valor_reais)')||js.includes('money(x.total_reais)'),
  "Mostrar valores financeiros por liga e IA");
assert.ok(js.includes('ns-inplay-total'),"Rodapé de métricas consolidadas");
assert.ok(js.includes('game.placar_minuto')&&js.includes('game.placar_final'),
  "Mostrar placares parcial e final");
assert.ok(js.includes('undo.push(current)'),"IA deve permitir desfazer mudanças");
console.log("Nostradamus ao vivo: múltiplas ligas, gols, pré-jogo, IA e financeiro.");
