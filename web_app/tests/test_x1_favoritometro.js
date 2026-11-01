/* Node.js unit tests: no server, database or DOM library needed. */
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");

const root={innerHTML:"",addEventListener(){}};
const context={document:{getElementById(id){return id==="x1-favoritometro"?root:null}},window:{},console};
vm.runInNewContext(fs.readFileSync("static/js/bets-x1-favoritometro.js","utf8"),context);
const api=context.window.X1Favoritometro;
assert.ok(api,"Favoritômetro inicializado");

function team(n,ppg,gf,ga,xg,xga,homePpg=2,awayPpg=1){
  const recent=[];
  for(let i=0;i<n;i++)recent.push({mando:i%2===0?"Casa":"Fora",pontos:i%2===0?homePpg:awayPpg});
  return {nome:"Clube",jogos:n,metricas:{
    media_pontos:ppg,media_gols_marcados:gf,media_gols_sofridos:ga,
    xg_por_jogo:xg,rival_xg_por_jogo:xga
  },cobertura:{xg:n,rival_xg:n},recente:recent};
}
const analysis={recorte:"20",temporada:"2026/2027",
  mandante:team(20,2.3,2.4,.7,2.2,.8),
  visitante:team(20,1.1,1.2,1.9,1.0,1.8)};
const prediction={
  mandante:{clube:"Mandante"},visitante:{clube:"Visitante"},
  probabilidades:{mandante:.59,empate:.23,visitante:.18}
};
const score=api.compute(analysis,prediction);
assert.ok(score.home>score.away,"Favorito esperado no mandante");
assert.equal(score.home+score.away,100);
assert.equal(score.prob.draw,.23);
assert.notEqual(score.home/100,score.prob.home,"Índice não é probabilidade 1X2");
assert.equal(score.signals.length,5);
assert.ok(api.why(score)[0].includes("Mandante"));
assert.ok(api.why(score)[1].includes("empate"));

const reverse=api.compute({...analysis,mandante:analysis.visitante,visitante:analysis.mandante},
 {...prediction,probabilidades:{mandante:.18,empate:.23,visitante:.59}});
assert.ok(reverse.home<reverse.away,"Favorito deve se inverter");

const short={...analysis,recorte:"5",mandante:team(5,2.3,2.4,.7,2.2,.8),visitante:team(5,1.1,1.2,1.9,1.0,1.8)};
const five=api.compute(short,prediction);
assert.ok(five.home>50);
assert.ok(five.signals.some(s=>s.name==="Pontos por jogo"&&s.realWeight<.15),"Shrinkage dos jogos curtos");

const missing=api.compute({mandante:{jogos:0,metricas:{}},visitante:{jogos:0,metricas:{}}},null);
assert.equal(missing,null,"Não inventar favoritsmo sem dados");
const one=api.compute({...analysis,mandante:team(1,2,3,0,3,0),visitante:team(1,2,3,0,3,0)},null);
assert.equal(one,null,"Uma partida sem modelo não sustenta índice");
console.log("Favoritômetro: testes aprovados.");
