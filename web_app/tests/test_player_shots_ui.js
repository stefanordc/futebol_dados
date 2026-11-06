const assert=require("node:assert/strict");
const fs=require("node:fs");
const script=fs.readFileSync("static/js/player-shots.js","utf8");
const profile=fs.readFileSync("static/js/entity.js","utf8");
const html=fs.readFileSync("templates/entity.html","utf8");
const css=fs.readFileSync("static/css/profiles.css","utf8");
const visuals=require("../static/js/shot-visuals.js");
assert.ok(profile.includes("[playerKeeper?'defesas':'finalizacoes'"));
assert.ok(profile.includes("state.data.penaltis_disponiveis"));
assert.ok(profile.includes("mountPlayerShots($('#player-shots-root')"));
assert.ok(html.includes("entity.js?v=player-shots-v1-20261106"));
assert.ok(html.includes("profiles.css?v=player-shots-v1-20261106"));
assert.ok(script.startsWith('import "./shot-visuals.js?v=player-visuals-v1-20261106"'));
assert.ok(css.includes(".player-shot-field")&&css.includes(".player-shot-goal"));

const code=script.split("\n").slice(1).join("\n")
  .replace("export async function mountPlayerShots","async function mountPlayerShots");
const view=new Function("window",code+";return {renderContent,percent,penalties,maps};")({
  DFShotMap:visuals
});
function shot(id,event,penalty=false){
  return {
    id,jogo_id:10,coordenada_x:94,coordenada_y:33,
    local_x_gol:32.78,altura_z_gol:1.2,mando:"Casa",
    tipo_evento:event,tipo_finalizacao:"Pé direito",
    minuto:27,data:"2026-11-04",campeonato:"Brasileiro",
    gol:event==="Gol",defesa:event==="Defendida",
    no_alvo:["Gol","Defendida"].includes(event),
    situacao_jogada:penalty?"Pênalti":"Jogada normal",
    atacante:"Adversário"
  };
}
const penalties={
  tentativas:2,acertos:1,acerto_pct:50,gols:1,defesas:1,no_alvo:2,
  lados:[
    {chave:"esquerda",label:"Esquerda",tentativas:2,gols:1,defesas:1,distribuicao_pct:100},
    {chave:"centro",label:"Centro",tentativas:0,gols:0,defesas:0,distribuicao_pct:0},
    {chave:"direita",label:"Direita",tentativas:0,gols:0,defesas:0,distribuicao_pct:0}
  ],
  alturas:[
    {chave:"rasteiro",label:"Rasteiro",tentativas:0,gols:0,defesas:0,distribuicao_pct:0},
    {chave:"meia_altura",label:"Meia-altura",tentativas:2,gols:1,defesas:1,distribuicao_pct:100},
    {chave:"alto",label:"Alto",tentativas:0,gols:0,defesas:0,distribuicao_pct:0}
  ],
  mapa:[shot(1,"Gol",true),shot(2,"Defendida",true)]
};
const data={
  tipo:"linha",cobertura:"Dados identificados",resumo:{
    tentativas:3,no_alvo:2,gols:1,defesas:1,acerto_pct:66.7
  },
  tipos:[{chave:"direito",label:"Pé direito",acerto_pct:66.7,
          tentativas:3,acertos:2,no_alvo:2}],
  mapa:[shot(1,"Gol"),shot(2,"Defendida"),shot(3,"Para fora")],
  penaltis:penalties
};
const filters={principal:"todos",penaltis:"todos"};
const chosen={principal:null,penaltis:null};
const output=view.renderContent(data,filters,chosen,"principal");
assert.ok(output.includes("Pé direito"));
assert.ok(output.includes("66,7%"));
assert.ok(output.includes("2 / 3"));
assert.ok(output.includes('class="shot-pitch-art"'));
assert.ok(output.includes('class="shot-goal-art"'));
assert.ok(output.includes("data-select-shot"));
assert.ok(!output.includes("Pênaltis cobrados"));
const penaltyView=view.renderContent(data,filters,chosen,"penaltis");
for(const name of ["Esquerda","Centro","Direita","Rasteiro","Meia-altura","Alto"])
  assert.ok(penaltyView.includes(name));
assert.ok(penaltyView.includes("0,0%"));
assert.ok(penaltyView.includes("50,0%"));
assert.ok(penaltyView.includes("gol de frente"));
assert.ok(!penaltyView.includes("Desempenho das finalizações"));
const keeperView=view.renderContent({...data,tipo:"goleiro"},filters,chosen,"principal");
assert.ok(keeperView.includes("Desempenho das defesas"));
assert.ok(keeperView.includes("Mapa das finalizações adversárias"));
const goaliePenalty=view.renderContent({...data,tipo:"goleiro"},filters,chosen,"penaltis");
assert.ok(goaliePenalty.includes("Lado do mergulho"));
assert.ok(!view.renderContent({...data,penaltis:null},filters,chosen,"penaltis").includes("Pênaltis cobrados"));
console.log("OK: jogadores de linha, goleiros, pênaltis, lados 0% e SVG compartilhado.");
