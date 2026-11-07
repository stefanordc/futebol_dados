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
assert.ok(Math.abs(coords.y-148.5)<.01,"Altura normalizada pela trave de 2,44 m");
assert.equal(view.goalPosition({local_x_gol:null,altura_z_gol:1.22}),null);
assert.ok(view.goalSvg({local_x_gol:32.78,altura_z_gol:1.22}).includes("<circle"),
  "Ponto de chegada na vista frontal");
assert.ok(!view.goalSvg({local_x_gol:null,altura_z_gol:null}).includes("<circle"),
  "Sem dados, não inventar ponto da bola");

for(const [html,entry] of [[page,"match.js"],[index,"home-premium.js"]]){
  assert.ok(html.includes(entry+(entry==="match.js"?"?v=sofa-lookup-v1-20261106":"?v=shotmap-v3-20261106")),
    "Página deve atualizar o cache do módulo de entrada");
  assert.ok(!html.includes('src="/static/js/shot-visuals.js"'),
    "Evitar carregamento clássico duplicado e dependência de ordem");
}
for(const file of [match,home]){
  assert.ok(file.startsWith('import "./shot-visuals.js?v=shotmap-v3-20261106";'),
    "Carregar obrigatoriamente o mapa antes da renderização");
}
assert.ok(match.includes("window.DFShotMap.shotPos(f)"),"Mapa usa correção lateral");
assert.ok(match.includes("window.DFShotMap.pitchSvg()"),"Campo desenhado em SVG");
assert.ok(match.includes("window.DFShotMap.goalSvg(f)"),"Vista frontal do gol");
assert.ok(!match.includes("window.DFShotMap?."),"Não ocultar falha de carregamento do mapa");

const start=match.indexOf("function sectionShotmap(finais, jogo) {");
const end=match.indexOf("function renderShotDetail(f) {",start);
assert.ok(start>=0&&end>start,"A seção de finalizações precisa existir");
const factory=new Function("window","shotPos","shotFiltroClass","shotClass","linkClube",
  match.slice(start,end)+"return sectionShotmap;");
const section=factory({DFShotMap:view},view.shotPos,()=>"gol",()=>"gol",(_,name)=>name);
const fixture=[{
  coordenada_x:95,coordenada_y:22,mando:"Casa",
  tipo_evento:"Gol",jogador:"Exemplo",minuto:19
}];
const markup=section(fixture,{casa_id:10,casa:"Casa",fora_id:11,fora:"Fora"});
assert.ok(markup.includes("shot-pitch-art"),"Deve incluir campo SVG completo");
assert.ok(markup.includes('data-i="0"'),"Deve incluir ponto da finalização");
assert.ok(markup.includes("shot-dot gol"),"Ponto de gol visível no mapa");
assert.ok(match.includes('renderShotDetail(finais[idx]);'),
  "Selecionar primeiro chute sem depender de coordenadas existentes");
assert.ok(home.includes("fullMatchDetails(data)"),"Painel lateral apresenta detalhes completos");
assert.ok(home.includes('href="/jogo/${id}"'),"Cabeçalho abre o jogo completo");
assert.ok(style.includes("body[data-page=\"match\"] .pitch-wrap"),
  "Mapa usa proporção verdadeira, não campo alargado");

console.log("OK: campo, gol de frente, espelhamento e detalhes da partida.");
