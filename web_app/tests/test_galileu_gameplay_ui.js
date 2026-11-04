/* Regressão estática: gameplay não vaza placares e não mistura dados do relatório legado. */
const fs=require("node:fs");
const assert=require("node:assert/strict");
const js=fs.readFileSync("static/js/galileu-gameplay.js","utf8");
const html=fs.readFileSync("templates/galileu.html","utf8");
const css=fs.readFileSync("static/css/galileu.css","utf8");
const py=fs.readFileSync("queries_galileu_gameplay.py","utf8");

const ids=[
  "gl-setup-form","gl-start-bank","gl-start-pct","gl-start-cutoff",
  "gl-start-stake","gl-bank-current","gl-bank-stake","gl-restart",
  "gl-round-title","gl-round-cutoff","gl-games","gl-games-closed","gl-round-results","gl-finish","gl-next",
  "gl-bulk-toolbar","gl-bulk-open","gl-bulk-info","gl-bulk-dialog",
  "gl-bulk-form","gl-bulk-stake","gl-bulk-count","gl-bulk-total","gl-bulk-confirm",
  "gl-month","gl-month-kpis","gl-month-groups","gl-close-form",
  "gl-month-confirmed","gl-close-deposit-choice","gl-close-withdraw-choice",
  "gl-close-stake-choice","gl-close-deposit","gl-close-withdraw",
  "gl-close-stake-type","gl-close-stake-value","gl-close-submit",
  "gl-close-bank-before","gl-close-bank-after","gl-close-stake-after",
  "gl-bank-original","gl-entry-dialog",
  "gl-entry-choice","gl-entry-method-button","gl-entry-manual-button",
  "gl-entry-method","gl-entry-market","gl-entry-stake",
  "gl-entry-confirm","gl-entry-cancel","gl-details-dialog",
];
for(const id of ids)assert.ok(html.includes('id="'+id+'"'),"Falta "+id);

assert.ok(html.includes("galileu-gameplay.js"),"Novo frontend deve ser carregado");
assert.ok(html.includes("galileu-gameplay-v18"),"Atualizar cache ao publicar");
assert.ok(js.includes('data-details="'+ "'+g.jogo_id+'"),"Cada jogo precisa abrir detalhes");
assert.ok(js.includes('data-entry=')&&js.includes('g.jogo_id'),"Fazer entrada em cada jogo");
assert.ok(js.includes('game.metodos.length?"method":"stats"'),
  "Método validado deve ser a aba inicial nos detalhes");
assert.ok(js.includes("Método validado"),"Carimbo visível");
assert.ok(js.includes('$("#gl-finish").addEventListener'),"Finalizar rodada");
assert.ok(js.includes('$("#gl-next").addEventListener'),"Próxima rodada");
assert.ok(html.indexOf('id="gl-next"')>html.indexOf('id="gl-close-submit"'),
  "Botão Próximo mês deve aparecer depois do fechamento mensal");
assert.ok(!html.includes('id="gl-month-history"') &&
  !js.includes('function renderHistory()'),
  "O histórico duplicado não deve aparecer no Galileu");
assert.equal(html.split('id="gl-next"').length-1,1,
  "Botão de avançar mês deve existir apenas uma vez");
assert.ok(css.includes(".gl-next-month-actions"),
  "Navegação após o fechamento mensal precisa de estilo");
assert.ok(js.includes('$("#gl-restart").addEventListener'),"Reiniciar progresso");
assert.ok(js.includes('$("#gl-close-form").addEventListener'),"Fechamento financeiro deve registrar decisões mensais");
assert.ok(js.includes('gl-entry-market'),"Entrada manual deve permitir mercado");
assert.ok(js.includes('gl-entry-method'),"Entrada com método deve solicitar método");
assert.ok(js.includes('done?"')||js.includes('const done=state.fase!=="aberta"'),
  "Placar condicionado à finalização");

/* Aviso de mês com zero entradas, específico do período atual. */
for(const id of ["gl-empty-month-dialog","gl-empty-month-title",
                 "gl-empty-month-description","gl-empty-month-back",
                 "gl-empty-month-continue"]){
  assert.ok(html.includes('id="'+id+'"'),"Aviso de mês vazio: "+id);
}
assert.ok(html.includes("Atenção: nenhuma entrada neste mês"),
  "O alerta precisa esclarecer o motivo");
assert.ok(html.includes(">Voltar</button>"),"Deve existir opção de voltar");
assert.ok(html.includes(">Seguir e finalizar mês</button>"),
  "Deve existir opção explícita para seguir");
assert.ok(py.includes('"entradas_mes":len(current)'),
  "Somente entradas do mês corrente podem definir o aviso");
assert.ok(js.includes('Number(state.entradas_mes||0)===0'),
  "Aviso somente quando não há entradas no mês");
assert.ok(js.includes('$("#gl-empty-month-dialog").showModal()'),
  "Deve exibir o aviso antes de finalizar");
assert.ok(js.includes('await request("/api/apostas/galileu/gameplay/estado")'),
  "Deve verificar entradas automaticamente registradas antes do aviso");
assert.ok(js.includes('$("#gl-empty-month-back").addEventListener'),
  "Voltar sem finalizar o mês");
assert.ok(js.includes('$("#gl-empty-month-continue").addEventListener'),
  "Seguir para finalizar com zero entradas");
assert.ok(css.includes(".gl-empty-month-dialog"),
  "Modal precisa de estilo visível e responsivo");

/* O alerta trimestral só aparece na tela de fechamento do mês. */
for(const id of ["gl-loss-streak-alert","gl-loss-streak-list"]){
  assert.ok(html.includes('id="'+id+'"'),"Alerta mensal ausente: "+id);
}
assert.ok(js.includes("function renderLossStreakAlerts()"),
  "Renderização do alerta mensal de método negativo");
assert.ok(js.includes("renderLossStreakAlerts();"),
  "Alerta deve aparecer no fechamento do mês");
assert.ok(py.includes("def _method_loss_streak_alerts(bets,method_catalog,month):"),
  "Cálculo por método e por mês de fechamento");
assert.ok(py.includes('"alertas_prejuizo_3_meses":_method_loss_streak_alerts('),
  "API deve devolver alertas somente no fechamento");

assert.ok(py.includes('response["_jogos_originais"]')===false,
  "Dados completos não devem ser retornados no estado do gameplay");
assert.ok(py.includes('if sess["fase"] in ("revelada","concluida")'),
  "Placar somente em rodada revelada");
assert.ok(py.includes('safe["placar"]'),
  "Placar liberado após finalizar");
assert.ok(py.includes('FOR UPDATE'),"Operações financeiras precisam bloquear sessão");
assert.ok(py.includes('COOKIE="galileu_gameplay"'),"Sessões persistentes por navegador");
assert.ok(py.includes('token_hash'),"Identificador do progresso deve ser armazenado em hash");
assert.ok(py.includes('COMMISSION=Decimal("0.045")'),"Lay a 4,5%");
assert.ok(css.includes(".gl-method-stamp"),"Carimbo visual");
assert.ok(css.includes(".gl-month-groups"),"Relatório mensal por grupos");

/* Ordenação das apostas só depois do fechamento, incluindo valores negativos. */
const vm=require("node:vm");
const sortStart=js.indexOf("function sortResultColumn(header){");
const sortEnd=js.indexOf('$("#gl-round-results").addEventListener("click"',sortStart);
assert.ok(sortStart>=0&&sortEnd>sortStart,"Ordenação pós-fechamento ausente");
const scope={};
vm.runInNewContext(js.slice(sortStart,sortEnd)+";this.sortResultColumn=sortResultColumn;",scope);
const cell=(text,number)=>({textContent:String(text),
  dataset:number===undefined?{}:{sortValue:String(number)}});
const makeRow=(name,value)=>({cells:[cell(name),cell("2 × 1"),
  cell("Under 3,5"),cell("under_35"),cell("1,65",1.65),
  cell("R$ 20,00",20),cell("green"),cell(String(value),value)]});
const row1=makeRow("Partida A",-20),row2=makeRow("Partida B",14.4),
      row3=makeRow("Partida C",3.25);
const tbody={rows:[row1,row2,row3],append(...items){this.rows=items;}};
const table={tBodies:[tbody],tHead:{rows:[{cells:[]}]},
  querySelectorAll(){return this.tHead.rows[0].cells;}};
const ths=Array.from({length:8},(_,i)=>({
  dataset:{resultSort:String(i)},attrs:{},
  closest:()=>table,
  getAttribute(k){return this.attrs[k]||"none";},
  setAttribute(k,v){this.attrs[k]=v;}
}));
table.tHead.rows[0].cells=ths;
scope.sortResultColumn(ths[7]);
assert.deepEqual(tbody.rows.map(r=>r.cells[0].textContent),
  ["Partida A","Partida C","Partida B"]);
scope.sortResultColumn(ths[7]);
assert.deepEqual(tbody.rows.map(r=>r.cells[0].textContent),
  ["Partida B","Partida C","Partida A"]);
assert.equal(ths[7].attrs["aria-sort"],"descending");
assert.ok(js.includes('TOTAL DO MÊS'),"Somatório não deve mudar ao ordenar");
assert.ok(js.includes('root.hidden=!revealed;'),"Mostrar tabela apenas após apurar");

console.log("Galileu gameplay: interface, rotas e sigilo de placar verificados.");

assert.ok(js.includes('state.corte_atual'),"Frontend exibe data de corte corrente");
assert.ok(js.includes('state.limite_janela'),"Frontend exibe fim do mês");
assert.ok(js.includes('state.pode_pular_vazio'),"Frontend suporta janelas vazias");
assert.ok(js.includes('"Avançar período sem jogos"'),"Mês vazio deve poder avançar");
assert.ok(!py.includes('cursor+timedelta(days=10)'),"Nenhuma janela de dez dias permanece");
assert.ok(py.includes('_month_end(first)'),"Backend limita janela ao último dia do mês");
assert.ok(py.includes('next_cut=limit'),"Avanço utiliza fim do mês");
assert.ok(py.includes('corte_atual=%s'),"Corte atualizado precisa persistir no Supabase");
assert.ok(py.includes('sess.get("corte_atual") or sess["corte"]'),"Leitura deve restaurar sessão existente");

/* Múltiplas entradas e fechamento individual. */
assert.ok(js.includes('const entries=g.entradas||[]'),
  "Card deve exibir todas as entradas do confronto, não apenas a última");
assert.ok(js.includes('data-game-card'),"Toda área do confronto deve abrir detalhes");
assert.ok(js.includes('event.target.matches("[data-game-card]")'),
  "Card deve abrir detalhes pelo teclado");
assert.ok(js.includes('data-finish-game'),"Card deve permitir Finalizar jogo");
assert.ok(js.includes('post("finalizar-jogo",{jogo_id:g.jogo_id})'),
  "O jogo finalizado precisa ser salvo no Supabase");
/* Retirada imediata de método em qualquer rodada. */
for(const id of ["gl-method-management","gl-disable-method-form",
                 "gl-disable-method-select","gl-disable-method-submit",
                 "gl-disabled-methods"]){
  assert.ok(html.includes('id="'+id+'"'),"Controle de métodos ausente: "+id);
}
assert.ok(js.includes('post("retirar-metodo",{metodo_id:id})'),
  "Retirada imediata deve chamar endpoint autenticado");
assert.ok(js.includes('renderMethodManagement();renderGames()'),
  "Jogos e métodos ativos devem ser atualizados após a retirada");
assert.ok(py.includes('def retirar_metodo(token,payload):'),
  "Endpoint deve cancelar pendentes e desativar método");
assert.ok(py.includes("AND tipo='metodo' AND status='pendente'"),
  "Cancelar apenas entradas pendentes do método");

assert.ok(js.includes('data-method-entry'),"Cada método tem botão de entrada");
assert.ok(js.includes('methodAlreadyEntered(game,m.id)'),
  "Não permitir repetir o método no mesmo confronto");
assert.ok(js.includes('showEntry(game,method.id)'),
  "Botão do método deve iniciar a entrada diretamente nele");
assert.ok(js.includes('availableMethods(entryGame)'),
  "Seletor de métodos só deve exibir métodos ainda não utilizados");
assert.ok(js.includes('!state.rodada_atual.jogos'),
  "Finalizar rodada não pode sumir quando todos os jogos saem da lista");
assert.ok(js.includes('state.resumo_rodada||[]'),
  "Fechamento da rodada inclui apostas de jogos finalizados individualmente");
assert.ok(py.includes('FROM galileu_private.jogos_finalizados'),
  "Fechamentos devem ser recuperados do Supabase");
assert.ok(py.includes('def finalizar_jogo(token,payload)'),
  "Backend deve permitir finalização individual");
assert.ok(py.includes('by_game=defaultdict(list)'),
  "Estado deve agrupar várias entradas por jogo");
assert.ok(py.includes('if g["jogo_id"] not in closed'),
  "Jogo finalizado não deve voltar à lista ativa");
assert.ok(py.includes('"resumo_rodada":resumo_rodada'),
  "Apuração da rodada inclui entradas do jogo removido");
assert.ok(html.includes('id="gl-games-closed"'),
  "Acompanhar quantos jogos foram removidos");

/* Confirmação rápida: só atualiza o card com a entrada gravada, sem /estado. */
assert.ok(js.includes('const result=await post("entrada",data);'),
  "Confirmar aguarda gravação real no backend");
assert.ok(js.includes('game.entradas.push(result.entrada)'),
  "Entrada retornada pelo Supabase deve aparecer no card imediatamente");
assert.ok(js.includes('state.entradas+=1'),
  "Contador total deve avançar após persistência");
assert.ok(js.includes('renderGames();'),
  "Só os cards precisam ser redesenhados após confirmar");
assert.ok(js.includes('}finally{'),
  "Botão deve ser liberado mesmo se a gravação falhar");
const submit=js.slice(js.indexOf('$("#gl-entry-form").addEventListener("submit"'),
                      js.indexOf('$("#gl-finish").addEventListener'));
assert.ok(!submit.includes('await mutate(()=>post("entrada",data))'),
  "Não buscar o estado completo após salvar uma entrada");
assert.ok(py.includes('RETURNING id'),"Backend deve devolver ID da entrada efetivamente salva");
assert.ok(py.includes('CACHE_SECONDS=15*60'),"Cache reduz novas consultas ao catálogo histórico");
assert.ok(py.includes('catalog is _history_catalog'),
  "Históricos de partidas não devem ser recalculados por entrada");
assert.ok(py.includes('selected=next((m for m in _methods() if m["id"]==method_id)'),
  "Backend só deve recalcular método solicitado");

/* Não listar jogos nem permitir escolha manual na nova interface. */
assert.ok(html.includes('id="gl-games" class="gl-games" hidden'),
  "Confrontos não devem aparecer antes da apuração");
assert.ok(js.includes('$("#gl-games").replaceChildren()'),
  "Não gerar cards de jogos pré-fechamento");
assert.ok(js.includes('$("#gl-bulk-toolbar").hidden=true'),
  "Não pedir confirmação de entradas em lote");
assert.ok(py.includes('for method in game["metodos"]:'),
  "Todos os métodos validados devem ser programados");
assert.ok(py.includes('ON CONFLICT DO NOTHING'),
  "Não registrar entrada duplicada após atualizar a página");
assert.ok(py.includes('"entradas_automaticas":auto_count'),
  "Estado deve informar novas entradas programadas automaticamente");
assert.ok(js.includes('availableMethods(game).map(method=>'),"Cada método disponível recebe uma seleção");
assert.ok(js.includes('methodAlreadyEntered(game,m.id)'),"Métodos já utilizados não podem ser repetidos");
assert.ok(!js.includes('bulkAvailableCents()'),"O lote não verifica saldo disponível");
assert.ok(js.includes('$("#gl-bulk-dialog").showModal()'),"Exibir prévia antes da confirmação");
assert.ok(js.includes('post("entradas-metodos",{'),"Salvar lote no backend");
assert.ok(js.includes('versao:state.versao'),"Validar versão da sessão antes de salvar");
assert.ok(js.includes('game.entradas.push(entry)'),"Atualizar cards com registros salvos");
assert.ok(js.includes('renderGames();'),"Reordenar e atualizar lotes após salvar");
assert.ok(py.includes('def registrar_metodos_em_lote(token,payload):'),"Implementar entrada em lote no backend");
assert.ok(py.includes('if int(sess["versao"])!=expected_version:'),"Prevenir envio de versão obsoleta");
assert.ok(!py.includes('if stake>Decimal(sess["banca_atual"]):'),
  "A stake individual pode superar a banca virtual");
assert.ok(py.includes('execute_values(cur,'),"Inserir lote na mesma transação");
assert.ok(py.includes('SELECT jogo_id,metodo_id FROM galileu_private.entradas'),
  "Remover entradas de métodos já registrados");
assert.ok(html.includes('id="gl-bulk-stake"'),"Stake de cada entrada deve ser editável");
assert.ok(html.includes('id="gl-bulk-list"'),"Prévia permite verificar todos os métodos");
assert.ok(css.includes('.gl-bulk-toolbar'),"Estilizar ação principal em lote");

/* Gestão mensal de stake e relatórios. */
assert.ok(js.includes('brl(state.banca_base_mes)'),"Banca exibida deve ser a base do mês");
assert.ok(js.includes('state.fechamento_pendente'),"Exigir fechamento quando mudar mês");
assert.ok(js.includes('$("#gl-next").disabled=Boolean(state.fechamento_pendente)'),
  "Bloquear próxima rodada antes do fechamento");
assert.ok(js.includes('post("fechar-mes",payload)'),"Registrar decisões da virada no servidor");
assert.ok(js.includes('"gl-close-deposit-choice"'),"Perguntar por aporte");
assert.ok(js.includes('"gl-close-withdraw-choice"'),"Perguntar por saque");
assert.ok(js.includes('"gl-close-stake-choice"'),"Perguntar reajuste de stake");
assert.ok(html.includes('href="/apostas/galileu/relatorios"'),"Aba Relatórios deve ser acessível");
assert.ok(py.includes('sess["banca_base_mes"] if sess.get("banca_base_mes") is not None'),
  "Stake percentual precisa usar banca-base mensal mesmo que seja zero");
assert.ok(py.includes('def fechar_mes(token,payload):'),
  "Fechamento mensal precisa ser transacional e persistido");
assert.ok(py.includes('def relatorios(token):'),"Relatórios precisam estar ligados à sessão atual");
assert.ok(py.includes('fechamentos_mensais'),"Armazenar histórico de fechamentos");
assert.ok(py.includes('galileu_private.movimentacoes'),"Armazenar aportes e saques auditáveis");


/* Seleção e liquidação irrestritas, inclusive com banca virtual negativa. */
for(const id of ["gl-bulk-all","gl-bulk-none","gl-bulk-feedback"]){
  assert.ok(html.includes('id="'+id+'"'),"Falta controle do lote: "+id);
}
for(const obsolete of ["gl-bulk-affordable","gl-bulk-fit-stake"]){
  assert.ok(!html.includes('id="'+obsolete+'"'),"Remover ajuste pelo saldo: "+obsolete);
}
assert.ok(html.includes('id="gl-bulk-stake" type="text" inputmode="decimal"'),
  "Aceitar stake em formato brasileiro");
assert.ok(js.includes('bulkSelectedOffers()'),"Enviar apenas os métodos selecionados");
assert.ok(js.includes('data-bulk-key'),"Selecionar método por partida");
assert.ok(js.includes("independentemente da banca"),"Avisar sobre apuração irrestrita");
assert.ok(js.includes('bulkSubmitting=true'),"Bloquear envio duplicado");
assert.ok(js.includes('stake:(preview.cents/100).toFixed(2)'),
  "Stake decimal normalizada");
assert.ok(!js.includes("preview.cents>preview.available"),"Sem limite por saldo no lote");
assert.ok(!js.includes("bulkMaxAffordable"),"Remover cálculo do máximo pela banca");

assert.ok(py.includes('def _liquidar_entradas_por_data(entries, by_id, banca_inicial):'),
  "Toda entrada deve ser liquidada");
assert.ok(!py.includes('status,pnl="sem_saldo"'),"Não marcar entrada nova como sem saldo");
assert.ok(!py.includes('if stake<=bank-committed:'),"Não limitar entradas simultâneas");
assert.ok(!py.includes('if bank<0:'),"Banca simulada pode ser negativa");
assert.ok(js.includes('state.exposicao_programada'),
  "Manter exposição informativa de entradas");

/* Fechamento mensal por método e retirada apenas para os meses seguintes. */
for(const id of ["gl-method-performance-title","gl-method-performance-table",
                 "gl-method-removal-note"]){
  assert.ok(html.includes('id="'+id+'"'),"Falta tabela de métodos: "+id);
}
assert.ok(js.includes("function renderMethodPerformance()"),"Tabela de métodos deve ser calculada no mês");
assert.ok(js.includes("item.maior_good_run")&&js.includes("item.maior_bad_run"),
  "Exibir ambas sequências máximas por método");
assert.ok(js.includes("data-remove-method"),"Checkbox individual para retirada futura");
assert.ok(js.includes("retirar_metodos:selectedMethodsToRemove()"),
  "Enviar métodos retirados no fechamento transacional");
assert.ok(py.includes("def _is_disabled(method_id,game_date,disabled):"),
  "Desativação deve considerar data do jogo");
assert.ok(py.includes("galileu_private.metodos_desativados"),
  "Persistir retirada por sessão no Supabase sem apagar estratégias");
