// Visualização de chutes: campo 105 × 68 m; destino da bola na largura 0..68 m.
(function(root){
  "use strict";
  const WIDTH=68,LENGTH=105,GOAL_WIDTH=7.32,GOAL_HEIGHT=2.44;
  const leftPost=(WIDTH-GOAL_WIDTH)/2,rightPost=(WIDTH+GOAL_WIDTH)/2;
  const num=x=>x===null||x===undefined||x===""?null:Number(x);
  const finite=x=>x!==null&&Number.isFinite(x);
  function shotPos(f){
    if(!f)return null;
    const x=num(f.coordenada_x),y=num(f.coordenada_y);
    if(!finite(x)||!finite(y)||x<0||x>LENGTH||y<0||y>WIDTH)return null;
    // Espelhamento lateral corrigido. Casa ataca para cima; Fora para baixo.
    const away=String(f.mando||"").toLowerCase()==="fora";
    const lateral=away?y:WIDTH-y;
    const longitudinal=away?x:LENGTH-x;
    return {
      left:100*(20+(lateral/WIDTH)*640)/680,
      top:100*(20+(longitudinal/LENGTH)*1010)/1050,
    };
  }
  function goalPosition(f){
    if(!f)return null;
    const x=num(f.local_x_gol),z=num(f.altura_z_gol);
    if(!finite(x)||!finite(z)||x<0||x>WIDTH||z<0||z>8)return null;
    // Traves: 30,34 m a 37,66 m. Não são coordenadas percentuais.
    const px=280+(WIDTH/2-x)*(416/GOAL_WIDTH);
    const py=218-z*(171/GOAL_HEIGHT);
    const inside=x>=leftPost&&x<=rightPost&&z<=GOAL_HEIGHT;
    return {x:px,y:py,inside,visible:px>=8&&px<=552&&py>=8&&py<=264};
  }
  const line='fill="none" stroke="rgba(255,255,255,.77)" stroke-width="2.6"';
  function pitchSvg(){
    const stripes=Array.from({length:10},(_,i)=>
      `<rect x="20" y="${20+i*101}" width="640" height="101" fill="${i%2?'#1c6839':'#207341'}"/>`).join("");
    const net=y=>`<g stroke="#fff" stroke-opacity=".65" fill="none">
      <rect x="303" y="${y}" width="74" height="13" rx="1.5" stroke-width="2.5"/>
      ${Array.from({length:8},(_,i)=>`<line x1="${303+i*10.57}" y1="${y}" x2="${303+i*10.57}" y2="${y+13}" stroke-width=".55"/>`).join("")}
      ${Array.from({length:3},(_,i)=>`<line x1="303" y1="${y+i*6.5}" x2="377" y2="${y+i*6.5}" stroke-width=".55"/>`).join("")}
    </g>`;
    return `<svg class="shot-pitch-art" viewBox="0 0 680 1050"
       role="img" aria-label="Campo de 105 por 68 metros com grande área, pequena área, pênaltis e gols."
       preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">
       <rect width="680" height="1050" rx="17" fill="#13552c"/>
       ${stripes}
       <rect x="20" y="20" width="640" height="1010" ${line}/>
       <path d="M20 525 H660" ${line}/>
       <circle cx="340" cy="525" r="87" ${line}/>
       <circle cx="340" cy="525" r="3.7" fill="#fff"/>
       <rect x="150.2" y="20" width="379.6" height="158.7" ${line}/>
       <rect x="253.8" y="20" width="172.4" height="52.9" ${line}/>
       <circle cx="340" cy="125.8" r="4" fill="#fff"/>
       <path d="M270.8 178.7 A87 87 0 0 0 409.2 178.7" ${line}/>
       <rect x="150.2" y="871.3" width="379.6" height="158.7" ${line}/>
       <rect x="253.8" y="977.1" width="172.4" height="52.9" ${line}/>
       <circle cx="340" cy="924.2" r="4" fill="#fff"/>
       <path d="M270.8 871.3 A87 87 0 0 1 409.2 871.3" ${line}/>
       <path d="M20 30 A10 10 0 0 0 30 20 M650 20 A10 10 0 0 0 660 30
                M20 1020 A10 10 0 0 1 30 1030 M650 1030 A10 10 0 0 1 660 1020" ${line}/>
       ${net(4)}${net(1033)}
    </svg>`;
  }
  function goalSvg(f){
    const p=goalPosition(f);
    const vertical=Array.from({length:11},(_,i)=>{
      const x=72+i*41.6;
      return `<line x1="${x.toFixed(2)}" y1="47" x2="${x.toFixed(2)}" y2="218"/>`;
    }).join("");
    const horizontal=Array.from({length:6},(_,i)=>{
      const y=47+i*34.2;
      return `<line x1="72" y1="${y.toFixed(2)}" x2="488" y2="${y.toFixed(2)}"/>`;
    }).join("");
    const ball=p&&p.visible?
      `<circle cx="${p.x.toFixed(2)}" cy="${p.y.toFixed(2)}" r="8.5"
         fill="${p.inside?'#ff923d':'#ffd265'}" stroke="#fff" stroke-width="3">
         <title>${p.inside?'Destino dentro da meta':'Finalização fora da moldura da meta'}</title>
       </circle>`:"";
    return `<svg class="shot-goal-art" viewBox="0 0 560 275"
      role="img" aria-label="${p?.visible?
         (p.inside?'Gol de frente com posição real da bola':'Gol de frente com ponto fora da meta'):
         'Gol de frente; destino da bola fora da escala disponível'}"
      xmlns="http://www.w3.org/2000/svg">
       <rect width="560" height="275" rx="12" fill="#106232"/>
       <path d="M0 237 Q280 226 560 237 V275 H0Z" fill="#0d542e"/>
       <path d="M72 47 L52 33 H508 L488 47 V218 L508 230 H52 L72 218Z"
         fill="rgba(2,25,14,.16)" stroke="rgba(255,255,255,.7)" stroke-width="1.5"/>
       <g stroke="rgba(255,255,255,.36)" stroke-width="1">${vertical}${horizontal}</g>
       <rect x="72" y="47" width="416" height="171" rx="1.5"
         fill="none" stroke="#fff" stroke-width="7"/>
       <path d="M72 218 H488" fill="none" stroke="#fff" stroke-width="3"/>
       ${ball}
    </svg>`;
  }
  const api={shotPos,goalPosition,pitchSvg,goalSvg,constants:{
    width:WIDTH,length:LENGTH,goalWidth:GOAL_WIDTH,goalHeight:GOAL_HEIGHT
  }};
  root.DFShotMap=api;
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
})(typeof window!=="undefined"?window:globalThis);
