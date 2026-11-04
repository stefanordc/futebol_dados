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
assert.ok(!html.includes('id="ns-inplay-odd" type="number" min="1.01" max="1000" step="0.01" value="2.00"'),
  "A odd não pode ser obrigatória nem ter preço fixo por padrão");
assert.ok(html.includes('placeholder="Automática por jogo"'),
  "Sem informar odd, deve haver estimativa automática por jogo");
assert.ok(html.includes('não uma cotação real')||html.includes('Não é uma odd histórica real'),
  "Explicitar limite das odds modeladas");
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
assert.ok(backend.includes('precos.cotar('),
  "Calcular odd por placar e minuto quando a cotação manual não for informada");
assert.ok(backend.includes('odd=c["odd_hipotetica"]'),
  "Quando informada, a odd manual prevalece sobre o modelo");
assert.ok(js.includes('quoteLabel(game.cotacao)'),
  "Identificar se a odd foi calculada pelo modelo ou informada pelo usuário");
assert.ok(js.includes('money(x.valor_reais)')||js.includes('money(x.total_reais)'),
  "Mostrar valores financeiros por liga e IA");
assert.ok(!html.includes('id="ns-inplay-odd" type="number" min="1.01" max="1000" step="0.01" value="2.00" required'),
  "Odd manual não pode impedir execução");
assert.ok(js.includes('ns-inplay-total'),"Rodapé de métricas consolidadas");
assert.ok(js.includes('game.placar_minuto')&&js.includes('game.placar_final'),
  "Mostrar placares parcial e final");
assert.ok(js.includes('undo.push(current)'),"IA deve permitir desfazer mudanças");
for(const id of ["ns-inplay-name","ns-inplay-save","ns-inplay-new",
                 "ns-inplay-saved","ns-inplay-saved-list"]){
  assert.ok(html.includes('id="'+id+'"'),"Salvar cenários: "+id);
}
assert.ok(js.includes('const savedURL="/api/apostas/nostradamus/ao-vivo/estrategias"'),
  "API de persistência separada da estratégia pré-jogo");
for(const method of ['method:id?"PATCH":"POST"','method:"DELETE"']){
  assert.ok(js.includes(method),"Métodos de salvamento devem existir: "+method);
}
for(const item of ['listar_cenarios','criar_cenario','editar_cenario','excluir_cenario']){
  assert.ok(backend.includes('def '+item+'('),"Backend de cenário ao vivo: "+item);
}
assert.ok(js.includes('Gravação não confirmada na nova leitura do banco.'),
  "Confirmar gravação no Supabase antes de informar sucesso");
assert.ok(js.includes('nostradamus/ao-vivo/estrategias'),
  "Não misturar cenários ao vivo com métodos pregame");
console.log("Nostradamus ao vivo: múltiplas ligas, gols, pré-jogo, IA e financeiro.");
