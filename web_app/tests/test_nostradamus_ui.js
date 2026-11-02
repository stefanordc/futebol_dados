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
assert.ok(html.includes("<th>Lucro médio/entrada (R$)</th>"),"Exibir lucro médio por aposta cotada");
assert.ok(html.includes("<th>Unidades (u)</th>"),"Mostrar unidades no resumo");
assert.ok(html.includes("<th>Resultado (R$)</th>"),"Mostrar resultado financeiro");
assert.ok(html.includes("<th>Good run máx.</th>"),"Mostrar maior sequência boa");
assert.ok(html.includes("<th>Bad run máx.</th>"),"Mostrar maior sequência ruim");
assert.ok(src.includes("money(r.lucro_medio_entrada)"),"Mostrar lucro médio de entradas com odds");
const summaryRender=src.slice(src.indexOf("function show(response){"),src.indexOf('$("#ns-summary").addEventListener("click"'));
assert.ok(summaryRender.includes("fmt(r.unidades,2)"),"Mostrar resultado em unidades");
assert.ok(summaryRender.includes("money(r.valor_reais)"),"Mostrar resultado financeiro em reais");
assert.ok(summaryRender.includes("fmt(r.maior_good_run,0)"),"Mostrar good run máximo");
assert.ok(summaryRender.includes("fmt(r.maior_bad_run,0)"),"Mostrar bad run máximo");
assert.ok(src.includes("esc(oddLabel(r))"),"Identificar origem da cotação por partida");
assert.ok(src.includes('fmt(r.historico_mandante,0)') && src.includes('fmt(r.historico_visitante,0)'),
  "Detalhamento informa quantos jogos entraram no histórico");

/* Estratégias persistidas: lista mostra datas do Supabase e não do corte. */
assert.ok(src.includes('Data de criação'),"Lista deve mostrar data de criação");
assert.ok(src.includes('Última atualização'),"Lista deve mostrar data da última edição");
assert.ok(src.includes('s.criado_em'),"Data de criação deve vir do banco");
assert.ok(src.includes('s.atualizado_em'),"Última edição deve vir do banco");
assert.ok(src.includes('data-rules') && src.includes('data-edit'),
  "Lista precisa manter visualizar regras e editar");
assert.ok(src.includes('timeZone:"America/Sao_Paulo"'),
  "Exibir timestamp no fuso brasileiro");
assert.ok(!src.includes('localStorage.setItem(store'),
  "Salvar estratégias exclusivamente no banco");
assert.ok(html.includes('nostradamus-select-all-v4'),
  "Forçar atualização do navegador com versionamento de estáticos");
const py=fs.readFileSync("queries_estrategias.py","utf8");
assert.ok(py.includes('ORDER BY criado_em DESC'),
  "Listar as estratégias por criação mais recente");

assert.ok(src.includes('cache:"no-store"'),"Buscar estratégias sem cache do navegador");
assert.ok(src.includes('const confirmed=stored.find('),
 "Verificar gravação relendo o registro no Supabase antes do sucesso");
assert.ok(src.includes('confirmada no Supabase.'),
 "Mensagem de sucesso somente após conferência");

assert.ok(src.includes('optgroup label="Dados físicos"'),"As métricas físicas devem formar uma categoria no seletor");
assert.ok(src.includes('metricOpts(meta.metricas,data.metrica)'),"O seletor de indicador deve aceitar métricas físicas");
assert.ok(src.includes('metricOpts(meta.metricas,data.metrica_ref)'),"Os indicadores físicos podem ser comparados com outros indicadores");

assert.ok(html.includes('id="ns-league-items"'),"Multi-seleção de ligas deve existir");
assert.ok(html.includes('id="ns-league-all"'),"Permitir selecionar todas as ligas");
assert.ok(src.includes("campeonato_ids:selectedLeagues()"),"Enviar lista de ligas no backtest");
assert.ok(src.includes("Array.isArray(saved.campeonato_ids)"),"Restaurar estratégias com várias ligas");
assert.ok(src.includes("saved.campeonato_id?[saved.campeonato_id]:[]"),
  "Manter compatibilidade com estratégias antigas");
assert.ok(src.includes("function closeLeagues()"),"Dropdown deve fechar ao usar Escape e clicar fora");

/* Favorito/zebra vem de odds reais e ganha o mando como detalhe, não como regra. */
assert.ok(js.includes('favorito:"Favorito (menor odd)"'),"Seletor deve priorizar favorito");
assert.ok(js.includes('zebra:"Zebra (maior odd)"'),"Seletor deve priorizar zebra");
assert.ok(js.includes('opts(favoriteMarkets,"back_favorito")'),"Back favorito é o padrão");
assert.ok(js.includes('roleLabel(c.lado,c.mando)'),"Mostrar Favorito/Zebra (Mandante/Visitante)");
assert.ok(js.includes('matchLabel(r)'),"Exibir favorito e zebra identificados nos detalhes");
assert.ok(js.includes('r.placar_favorito||r.placar'),"Placar segue a ordem favorito x zebra quando possível");
assert.ok(js.includes('saved.objetivo||"back_favorito"'),"Estratégia nova inicia no favorito");
assert.ok(js.includes('estratégia antiga'),"Preservar identificação dos mercados legados");
assert.ok(html.includes('menor odd de vitória no Match Odds'),"Explicar critério de odds");

/* A ação em lote não substitui nem altera a lógica dos filtros individuais. */
assert.ok(html.includes('id="ns-league-select-all"'),"Botão Selecionar todos deve existir");
assert.ok(html.includes('>Selecionar todos</button>'),"Rótulo deve ser explícito");
assert.ok(html.includes('Sem filtro (todos)'),"Permitir limpar filtros e usar todas as ligas");
assert.ok(src.includes('$("#ns-league-select-all").addEventListener("click"'),
  "Clique deve selecionar todas as ligas");
assert.ok(src.includes('setLeagues(ids);'),"Seleção em lote deve usar a mesma função das escolhas individuais");
assert.ok(src.includes('allButton.disabled=total===0||ids.length===total;'),
  "Ação deve desabilitar sem ligas disponíveis ou após selecionar todas");
assert.ok(css.includes('.ns-league-actions'),"Ações em lote devem ter layout próprio");
