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
  "gl-month","gl-month-kpis","gl-month-groups","gl-adjust-form",
  "gl-adjust-type","gl-adjust-value","gl-entry-dialog",
  "gl-entry-choice","gl-entry-method-button","gl-entry-manual-button",
  "gl-entry-method","gl-entry-market","gl-entry-stake",
  "gl-entry-confirm","gl-entry-cancel","gl-details-dialog",
];
for(const id of ids)assert.ok(html.includes('id="'+id+'"'),"Falta "+id);

assert.ok(html.includes("galileu-gameplay.js"),"Novo frontend deve ser carregado");
assert.ok(html.includes("galileu-gameplay-v5"),"Atualizar cache ao publicar");
assert.ok(js.includes('data-details="'+ "'+g.jogo_id+'"),"Cada jogo precisa abrir detalhes");
assert.ok(js.includes('data-entry=')&&js.includes('g.jogo_id'),"Fazer entrada em cada jogo");
assert.ok(js.includes('game.metodos.length?"method":"stats"'),
  "Método validado deve ser a aba inicial nos detalhes");
assert.ok(js.includes("Método validado"),"Carimbo visível");
assert.ok(js.includes('$("#gl-finish").addEventListener'),"Finalizar rodada");
assert.ok(js.includes('$("#gl-next").addEventListener'),"Próxima rodada");
assert.ok(js.includes('$("#gl-restart").addEventListener'),"Reiniciar progresso");
assert.ok(js.includes('$("#gl-adjust-form").addEventListener'),"Reajuste ao fim do mês");
assert.ok(js.includes('gl-entry-market'),"Entrada manual deve permitir mercado");
assert.ok(js.includes('gl-entry-method'),"Entrada com método deve solicitar método");
assert.ok(js.includes('done?"')||js.includes('const done=state.fase!=="aberta"'),
  "Placar condicionado à finalização");

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
console.log("Galileu gameplay: interface, rotas e sigilo de placar verificados.");

assert.ok(js.includes('state.corte_atual'),"Frontend exibe data de corte corrente");
assert.ok(js.includes('state.limite_janela'),"Frontend exibe limite de dez dias/fim do mês");
assert.ok(js.includes('state.pode_pular_vazio'),"Frontend suporta janelas vazias");
assert.ok(js.includes('"Avançar período sem jogos"'),"Período vazio deve poder avançar sem revelar placar");
assert.ok(py.includes('cursor+timedelta(days=10)'),"Backend limita janela a dez dias");
assert.ok(py.includes('_month_end(first)'),"Backend limita janela ao último dia do mês");
assert.ok(py.includes('"proximo_corte":next_cut'),"Avanço utiliza maior data exibida");
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
