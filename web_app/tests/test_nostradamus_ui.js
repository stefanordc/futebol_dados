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
assert.ok(html.includes('nostradamus-inplay-v2'),
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
assert.ok(src.includes('indicatorOpts(meta.metricas,meta.mercados_odd,'),"O seletor Indicador deve aceitar estatísticas e mercados de odds");
assert.ok(src.includes('metricOpts(meta.metricas,data.metrica_ref)'),"Os indicadores físicos podem ser comparados com outros indicadores");

assert.ok(html.includes('id="ns-league-items"'),"Multi-seleção de ligas deve existir");
assert.ok(html.includes('id="ns-league-all"'),"Permitir selecionar todas as ligas");
assert.ok(src.includes("campeonato_ids:selectedLeagues()"),"Enviar lista de ligas no backtest");
assert.ok(src.includes("Array.isArray(saved.campeonato_ids)"),"Restaurar estratégias com várias ligas");
assert.ok(src.includes("saved.campeonato_id?[saved.campeonato_id]:[]"),
  "Manter compatibilidade com estratégias antigas");
assert.ok(src.includes("function closeLeagues()"),"Dropdown deve fechar ao usar Escape e clicar fora");

/* Favorito/zebra vem de odds reais e ganha o mando como detalhe, não como regra. */
assert.ok(js.includes('favorito:"Favorito"'),"Seletor deve exibir somente Favorito");
assert.ok(js.includes('zebra:"Zebra"'),"Seletor deve exibir somente Zebra");
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

/* Mapeamento legado e regras de odd com mercado explícito. */
assert.ok(src.includes('const legacyRole={mandante:"favorito",visitante:"zebra"}'),
 "O editor converte estratégias antigas ao abrir");
assert.ok(src.includes('ambos:"Ambos (cada equipe)"'),
 "Equipe analisada deve oferecer Ambos");
assert.ok(src.includes('const indicatorOpts=(metrics,markets,selected)=>'),
 "Um único indicador deve reunir estatística e odds");
assert.ok(src.includes('<optgroup label="Odds dos mercados">'),
 "O mercado de odds deve estar no mesmo seletor que as estatísticas");
assert.ok(src.includes('class="ns-odd-min"') && src.includes('class="ns-odd-max"'),
 "A interface recebe odds mínima e máxima");
assert.ok(src.includes('indicatorOpts(meta.metricas,meta.mercados_odd,'),
 "Os mercados disponíveis vêm do backend e dividem o campo com as estatísticas");
assert.ok(src.includes('tipo:"odd",mercado:indicator.slice(4)'),
 "Uma estratégia salva deve guardar o mercado escolhido dentro de Indicador");
assert.ok(src.includes('c.tipo==="odd"'),
 "A tela de detalhes deve exibir os filtros de odds executados");
assert.ok(css.includes('.ns-odd-criterion[hidden]'),
 "Campos ocultos não devem aparecer no grid de critérios");

/* Mando: campo logo após a seleção Favorito/Zebra/Ambos. */
const sidePosition=src.indexOf('class="ns-side"');
const homePosition=src.indexOf('class="ns-home-filter"');
const metricPosition=src.indexOf('class="ns-metric"');
assert.ok(sidePosition>=0&&homePosition>sidePosition&&metricPosition>homePosition,
  "Mando de campo deve aparecer imediatamente após Equipe analisada");
assert.ok(src.includes('opts({indiferente:"Indiferente",mandante:"Mandante",visitante:"Visitante"}'),
  "As três opções de mando devem estar disponíveis");
assert.ok(src.includes('mando_preferido:row.querySelector(".ns-home-filter").value'),
  "O mando selecionado deve ser enviado no payload e persistido nos critérios");
assert.ok(src.includes('item.mando_preferido:"indiferente"'),
  "Estratégias antigas sem mando devem usar Indiferente");
assert.ok(src.includes('mando.disabled=both'),
  "Para Ambos, o mando não pode restringir as duas equipes");
assert.ok(src.includes('if(both)mando.value="indiferente"'),
  "Ambos força Indiferente em vez de criar filtro impossível");
assert.ok(src.includes('rule.mando_preferido'),
  "Visualização das regras salvas deve exibir o filtro de mando");
assert.ok(css.includes('.ns-home-filter-wrap'),
  "Mando de campo deve ter estilos responsivos próprios");

/* Critério integrado: não deve existir seletor de tipo nem campo duplicado de mercado. */
assert.ok(!src.includes("ns-condition-kind"),
  "Remover seletor Tipo de critério");
assert.ok(!src.includes("ns-odd-market"),
  "Remover seletor separado Mercado da odd");
assert.ok(src.includes('value.startsWith("odd:")'),
  "Mudança de indicador precisa alternar campos de estatística e odd");
assert.ok(src.includes('data.tipo==="odd"?"odd:"+data.mercado:data.metrica'),
  "Abrir estratégia salva deve restaurar o indicador correto");
assert.ok(src.includes('opts(odds,selected)'),
  "Odds reais da metadata precisam constar no mesmo dropdown");
assert.ok(src.includes('row.classList.toggle("ns-odd-active",isOdd)'),
  "O layout deve reagir à seleção de uma odd");
assert.ok(css.includes('.ns-condition.ns-odd-active .ns-indicator-field'),
  "O campo indicador deve manter destaque também ao selecionar odds");
assert.ok(html.includes('as estatísticas e as <strong>odds dos mercados</strong> aparecem juntas'),
  "Documentar a disposição unificada dos indicadores");

/* O assistente recomenda limites de odds e indicadores sem salvar automaticamente. */
assert.ok(html.includes('id="ns-ai-panel"'),"Otimização deve aparecer no painel de resultados");
assert.ok(html.includes('id="ns-ai-run"'),"Botão de análise de oportunidades");
assert.ok(js.includes('"/api/apostas/nostradamus/otimizar"'),
  "Análise busca sugestões do backend com recorte cronológico");
assert.ok(js.includes('JSON.stringify(lastSimulationConfig)'),
  "A data de corte aplicada ao backtest deve ser preservada na otimização");
assert.ok(js.includes('data-ai-apply'),"O usuário pode escolher aplicar um critério");
assert.ok(js.includes('conditionLine(candidate)'),
  "Botão Adicionar regra deve apenas adicionar a condição ao formulário");
assert.ok(!js.includes('conditionLine(aiSuggestions[index].condicao)'),
  "Não acoplar o botão de sugestão à simulação automática");
assert.ok(js.includes('$("#ns-form").requestSubmit()'),
  "Atalho Testar alterações deve executar a simulação separadamente");
assert.ok(js.includes('btn.textContent=suggestion.acao==="remover"?"Regra removida":"Regra adicionada"'),
  "Botão de sugestão confirma inclusão ou remoção sem salvar");
assert.ok(!js.includes('localStorage.setItem(store'),"Análise não deve salvar a estratégia silenciosamente");
assert.ok(css.includes('.ns-ai-panel'),"Painel da otimização deve ser estilizado");

/* O total deve estar no rodapé da tabela, sem somar métricas não aditivas. */
assert.ok(html.includes('<tfoot id="ns-summary-total" hidden>'),"Rodapé Total deve existir na própria tabela");
assert.ok(html.includes('id="ns-summary-coverage"'),"Mostrar cobertura de odds no agregado");
assert.ok(src.includes('const grand=response.total;'),"Total deve vir do acumulador exato do backend");
assert.ok(src.includes('footer.innerHTML=\'<tr class="ns-total-row">\''),"Renderizar a linha Total");
assert.ok(src.includes('<th scope="row">TOTAL</th>'),"Destacar total como rótulo de linha");
assert.ok(src.includes('fmt(grand.entradas,0)')&&src.includes('fmt(grand.greens,0)')&&
  src.includes('fmt(grand.reds,0)'),"Somar quantidade de entradas e greens/reds");
assert.ok(src.includes('fmt(grand.win_rate,1)'),"Win Rate consolidado, não média simples");
assert.ok(src.includes('fmt(grand.unidades,2)'),"Unidades consolidadas");
assert.ok(src.includes('money(grand.valor_reais)'),"Resultado financeiro consolidado");
assert.ok(src.includes('fmt(grand.odd_media,2)'),"Odd média ponderada pelas entradas cotadas");
assert.ok(src.includes('money(grand.lucro_medio_entrada)'),"Lucro médio ponderado por entrada cotada");
assert.ok(src.includes('fmt(grand.maior_good_run,0)')&&src.includes('fmt(grand.maior_bad_run,0)'),
  "Mostrar sequências cronológicas globais");
assert.ok(src.includes('fmt(grand.cotadas,0)'),"Explicar entradas cotadas do agregado");
assert.ok(css.includes('#ns-summary-total .ns-total-row'),"Estilo próprio do rodapé");

/* A IA pode incluir ou remover condições com histórico de desfazer. */
assert.ok(html.includes('id="ns-ai-go-conditions"'),"Atalho Ir aos critérios");
assert.ok(html.includes('id="ns-ai-test-shortcut"'),"Atalho Testar alterações");
assert.ok(html.includes('id="ns-ai-save-shortcut"'),"Atalho Salvar estratégia");
assert.ok(html.includes('id="ns-ai-undo"'),"Atalho Desfazer última mudança");
assert.ok(src.includes('?"Remover regra":"Adicionar regra"'),"Cartões devem distinguir inclusão e remoção");
assert.ok(src.includes('item.acao==="remover"'),"Sugestões de remoção devem ser explícitas");
assert.ok(!src.includes('Adicionar critério e testar'),"Não executar teste automaticamente ao incluir sugestão");
assert.ok(src.includes('if(suggestion.acao==="remover")'),"Aplicar remoção somente quando a IA indicar");
assert.ok(src.includes('current.findIndex(item=>JSON.stringify(item)===JSON.stringify(expected))'),
 "Remoção compara com a regra original e evita remover critério errado");
assert.ok(src.includes('aiUndoStack.push(current)'),"Manter histórico das alterações sugeridas");
assert.ok(src.includes('const previous=aiUndoStack.pop()'),"Desfazer precisa restaurar regras anteriores");
assert.ok(css.includes('.ns-ai-shortcuts'),"Atalhos devem estar visíveis e responsivos");

assert.ok(src.includes('"lay_goleada_visitante"].includes(k)'),
  "O objetivo visitante legado deve aparecer apenas no grupo de estratégias antigas");
assert.ok(html.includes("zebra é o clube com maior odd de vitória"),
  "Explicar a diferença entre zebra e visitante no formulário");

/* Mercado derivado de Correct Score: back/lay dos dois lados e transparência. */
assert.ok(src.includes('function goleadaQuotes(row)'),
  "Exibir quatro odds estimadas ao abrir jogos com mercado de goleada");
assert.ok(src.includes('q.back_goleada_mandante')&&src.includes('q.back_goleada_visitante'),
  "Mostrar Back goleada de mandante e visitante");
assert.ok(src.includes('q.lay_goleada_mandante')&&src.includes('q.lay_goleada_visitante'),
  "Mostrar Lay goleada de mandante e visitante");
assert.ok(src.includes('r.tipo_odd==="modelo_cs_lay"'),
  "Marcar Lay como estimativa derivada do Correct Score");
assert.ok(src.includes('r.tipo_odd==="modelo_cs_back"'),
  "Marcar Back como estimativa derivada do Correct Score");
assert.ok(html.includes('as 16 odds Correct Score'),
  "Explicar a origem probabilística das novas odds");
