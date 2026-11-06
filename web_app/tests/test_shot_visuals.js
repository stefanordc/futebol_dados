// Executar em web_app/: node tests/test_shot_visuals.js
const assert=require("node:assert/strict");
const fs=require("node:fs");
const view=require("../static/js/shot-visuals.js");
const match=fs.readFileSync("static/js/match.js","utf8");
const home=fs.readFileSync("static/js/home-premium.js","utf8");
const page=fs.readFileSync("templates/match.html","utf8");
const index=fs.readFileSync("templates/index.html","utf8");
const style=fs.readFileSync("static/css/app.css","utf8");

const casa=view.shotPos({coordenada_x:95,coordenada_y:22,mando:"Casa"});
const fora=view.shotPos({coordenada_x:95,coordenada_y:22,mando:"Fora"});
assert.ok(casa.left>50,"Casa deve ter lateral espelhada");
assert.ok(fora.left<50,"Fora ocupa lateral oposta após rotação");
assert.ok(casa.top<30,"Finalização de casa próxima ao gol superior");
assert.ok(fora.top>70,"Finalização de fora próxima ao gol inferior");
assert.equal(view.shotPos({coordenada_x:null,coordenada_y:40,mando:"Casa"}),null);
assert.equal(view.shotPos({coordenada_x:95,coordenada_y:null,mando:"Casa"}),null);

const field=view.pitchSvg();
assert.ok(field.includes('viewBox="0 0 680 1050"'),"Proporção do campo");
assert.ok(field.includes('width="379.6"'),"Grande área");
assert.ok(field.includes('width="172.4"'),"Pequena área");
assert.ok(field.includes('circle cx="340" cy="125.8"'),"Marca do pênalti");
assert.ok(field.includes("A87 87"),"Meia-lua da área");
assert.ok(field.includes('y="1033"'),"Gol inferior");

const coords=view.goalPosition({local_x_gol:32.78,altura_z_gol:1.22});
assert.ok(coords.inside&&coords.visible,"Gol com posição registrada na meta");
assert.ok(coords.x>280,"Eixo lateral corrigido");
assert.ok(Math.abs(coords.y-132.5)<.01,"Altura normalizada pela trave de 2,44 m");
assert.equal(view.goalPosition({local_x_gol:null,altura_z_gol:1.22}),null);
assert.ok(view.goalSvg({local_x_gol:32.78,altura_z_gol:1.22}).includes("<circle"),
  "Ponto de chegada na vista frontal");
assert.ok(!view.goalSvg({local_x_gol:null,altura_z_gol:null}).includes("<circle"),
  "Sem dados, não inventar ponto da bola");

for(const html of [page,index]){
  assert.ok(html.includes("shot-visuals.js?v=shotmap-v2-20261106"),
    "Páginas carregam mapeamento compartilhado");
}
assert.ok(match.includes("window.DFShotMap?.shotPos(f)"),"Mapa usa correção lateral");
assert.ok(match.includes("window.DFShotMap?.pitchSvg()"),"Campo desenhado em SVG");
assert.ok(match.includes("window.DFShotMap?.goalSvg(f)"),"Vista frontal do gol");
assert.ok(home.includes("fullMatchDetails(data)"),"Painel lateral apresenta detalhes completos");
assert.ok(home.includes('href="/jogo/${id}"'),"Cabeçalho abre o jogo completo");
assert.ok(style.includes("body[data-page=\"match\"] .pitch-wrap"),
  "Mapa usa proporção verdadeira, não campo alargado");

console.log("OK: campo, gol de frente, espelhamento e detalhes da partida.");
