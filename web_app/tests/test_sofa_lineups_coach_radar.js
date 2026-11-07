// Executar de web_app/: node tests/test_sofa_lineups_coach_radar.js
const assert=require("node:assert/strict");
const fs=require("node:fs");
const match=fs.readFileSync("static/js/match.js","utf8");
const radar=fs.readFileSync("static/js/profile-radar.js","utf8");
const matchHtml=fs.readFileSync("templates/match.html","utf8");
const entityHtml=fs.readFileSync("templates/entity.html","utf8");
const css=fs.readFileSync("static/css/app.css","utf8");
const start=match.indexOf("function idSofascore(");
const end=match.indexOf("const PLAYER_STAT_ROWS",start);
assert.ok(start>0&&end>start,"Escalação com componente Sofascore disponível");
const lineupFactory=new Function(
  "document","logo","linkClube","linkTecnico","linkJogador","playerNode","ratingClass","n",
  match.slice(start,end)+"return {idSofascore,sofaLineupsMarkup,sectionEscalacao};"
);
const lineup=lineupFactory(
  {documentElement:{getAttribute:()=>"dark"}},
  ()=>"",(_,name)=>name,(_,name)=>name,(_,name)=>name,()=>"",
  ()=>"",x=>String(x)
);
assert.equal(lineup.idSofascore("15238233"),15238233);
assert.equal(lineup.idSofascore("15238233<script>"),null);
assert.equal(lineup.idSofascore(""),null);
const empty={titulares:[],reservas:[]};
const game={
  id_sofascore:15238233,casa:"Palmeiras",fora:"Remo",
  casa_id:92,fora_id:98,tecnico_casa:"A",tecnico_fora:"B"
};
const html=lineup.sectionEscalacao({casa:empty,fora:empty},game);
assert.ok(html.includes('src="https://widgets.sofascore.com/pt-BR/embed/lineups?id=15238233&widgetTheme=dark"'));
assert.ok(html.includes("Campo do Sofascore")&&html.includes("Campo do site"));
assert.ok(html.includes("id=\"sofa-lineups\""));
assert.ok(html.includes('id="lineup-local" hidden'));
assert.ok(html.includes("lineup-grid"),"Manter campo e jogadores originais");
const missing=lineup.sectionEscalacao({casa:empty,fora:empty},{...game,id_sofascore:null});
assert.ok(!missing.includes("sofa-lineups-embed"),"Não usar ID de outra partida");
assert.ok(missing.includes("Verificando automaticamente a escalação do Sofascore"));
assert.ok(missing.includes("lineup-grid"));
assert.ok(missing.includes('id="lineup-sofa-lookup"'),"Resolver deve aparecer em jogos sem ID");
assert.ok(missing.includes('id="lineup-sofa-form"'),"Permitir vínculo manual pelo URL Sofascore");
assert.ok(missing.includes('id="lineup-local"'),"Campo interno permanece como alternativa");
assert.ok(match.includes('fetch(`/api/jogo/${jogo.id}/sofascore-escalacao`)'),
  "Consultar correspondência de partida pelo backend");
assert.ok(match.includes('method:"POST"'),
  "Permitir salvar ID fornecido pelo usuário");
assert.ok(match.includes("lineup-sofa-status-warning"),"Exibir aviso visual quando não encontra ID");
assert.ok(css.includes(".lineup-sofa-status-warning"),"Alerta deve ser visualmente destacado");
assert.ok(match.includes('activateSofaLineups(data.id)'),
  "Ativar widget sem recarregar a página");
assert.ok(css.includes(".sofa-lineups-iframe"));
assert.ok(css.includes(".lineup-local[hidden]"));
assert.ok(matchHtml.includes("match.js?v=sofa-dados-fisicos-v1-20261106"));
assert.ok(entityHtml.includes("profile-radar.js?v=sofa-radar-v1-20261106"));

const cs=radar.indexOf("async function coachRadar(");
const ce=radar.indexOf("const SPECIAL_LABELS",cs);
assert.ok(cs>0&&ce>cs,"Radar do técnico existente");
assert.ok(!radar.slice(cs,ce).includes("/api/clube/"),"Radar não deve buscar páginas de clubes");
assert.ok(!radar.slice(cs,ce).includes("/api/jogo/"),"Radar não deve buscar centenas de jogos");
let queried=[];
const stats={
  jogos:11,gols_marcados:16,gols_sofridos:21,clean_sheets:2,
  vitorias:2,empates:4,finalizacoes:133,jogos_finalizacoes:11,
  xg:14.39,jogos_xg:11,grandes_chances:23,jogos_chances:11,
  bloqueios:37,jogos_bloqueios:11,interceptacoes:84,jogos_interceptacoes:11,
  passes_certos:3431,jogos_passes:11
};
const coachFactory=new Function(
  "scope","$","get","number","sixTeam","combine","sequence","idInUrl","CLUB_LABELS","CLUB_NOTES",
  radar.slice(cs,ce)+"return coachRadar;"
);
const coach=coachFactory(
  ()=>new URLSearchParams({temporada:"2026/2027"}),
  selector=>selector.includes("camp")?{value:"7"}:{value:"92"},
  async uri=>{queried.push(uri);return {jogos:11,metricas:stats,aviso:null};},
  value=>value==null?null:Number(value),
  data=>{
    assert.equal(data.games,11);
    assert.equal(data.shots,133);
    return [72,50,69,62,56,45];
  },
  (...items)=>items.filter(x=>x!=null).reduce((a,b)=>a+b,0)/items.length,
  1,8,["Ataque","Defesa","Criatividade","Gols","Evitar gols","Eficiência"],["A","B","C","D","E","F"]
);
(async()=>{
  const summary=await coach(()=>{},1);
  assert.equal(queried.length,1,"Radar faz UMA requisição");
  assert.ok(queried[0].includes("/api/tecnico/8/radar?"));
  assert.ok(queried[0].includes("temporada=2026%2F2027"));
  assert.ok(queried[0].includes("campeonato_id=7"));
  assert.ok(queried[0].includes("clube_id=92"));
  assert.equal(summary.values.length,6);
  assert.ok(summary.subtitle.includes("11 partidas"));
  console.log("OK: escalação Sofascore e radar SQL do técnico.");
})().catch(error=>{console.error(error);process.exitCode=1;});
