/* Dados Futebol — x1. Projeções carregadas da API; não fabrica dados ausentes. */
(() => {
  "use strict";
  const $ = (q,root=document)=>root.querySelector(q);
  const esc = value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const percent = n=>n==null?"—":(n*100).toLocaleString("pt-BR",{minimumFractionDigits:1,maximumFractionDigits:1})+"%";
  const num=(n,d=2)=>n==null?"—":Number(n).toLocaleString("pt-BR",{minimumFractionDigits:d,maximumFractionDigits:d});
  const league=$("#x1-campeonato"),season=$("#x1-temporada"),home=$("#x1-mandante"),away=$("#x1-visitante");
  const feedback=$("#x1-feedback"),results=$("#x1-resultados");
  let data=null,fetchId=0,clubs=[];
  const markets=[
    ["over_05_ht","Over 0,5 HT"],["over_05_ft","Over 0,5 FT"],
    ["over_15","Over 1,5 FT"],["over_25","Over 2,5 FT"],
    ["over_35","Over 3,5 FT"],["under_35","Under 3,5 FT"],
    ["ambos_marcam","Ambos marcam"],["goleada_mandante","Goleada do mandante"],
    ["goleada_visitante","Goleada do visitante"],
    ["mandante_1x0_60","Mandante 1x0 no minuto 60"],
    ["visitante_1x0_60","Visitante 1x0 no minuto 60"],
    ["mandante_abrir","Mandante abre o placar"],
    ["visitante_abrir","Visitante abre o placar"]
  ];
  const oddsNames=[
    ["mandante","Back mandante"],["visitante","Back visitante"],
    ["over_05_ft","Back over 0,5 FT"],["over_15","Back over 1,5 FT"],
    ["over_25","Back over 2,5 FT"],["ambos_marcam","Back ambos marcam"],
    ["lay_mandante","Lay mandante"],["lay_visitante","Lay visitante"],
    ["lay_goleada_mandante","Lay goleada mandante"],
    ["lay_goleada_visitante","Lay goleada visitante"],
    ["lay_1x0","Lay 1x0"],["lay_0x1","Lay 0x1"]
  ];
  function message(msg,type="info"){feedback.innerHTML='<div class="x1-message '+type+'">'+esc(msg)+'</div>';}
  async function get(url){
    const response=await fetch(url);
    let json;
    try{json=await response.json();}catch{throw Error("O servidor retornou uma resposta inválida.");}
    if(!response.ok)throw Error(typeof json.detail==="string"?json.detail:"Erro "+response.status+" ao consultar as informações.");
    return json;
  }
  const opt=(value,text)=>'<option value="'+esc(value)+'">'+esc(text)+'</option>';
  function setOptions(el,rows,placeholder,render){
    el.innerHTML=opt("",placeholder)+rows.map(render).join("");
    el.disabled=rows.length===0;
  }
  function renderClubs(){
    const currentHome=home.value,currentAway=away.value;
    setOptions(home,clubs,"Escolha o mandante",c=>opt(c.id,c.clube));
    setOptions(away,clubs,"Escolha o visitante",c=>opt(c.id,c.clube));
    if(clubs.some(c=>String(c.id)===currentHome))home.value=currentHome;
    if(clubs.some(c=>String(c.id)===currentAway))away.value=currentAway;
  }
  async function loadMeta(){
    const id=league.value,request=++fetchId;
    if(!id){
      setOptions(season,[],"Escolha a temporada",()=> "");
      clubs=[];renderClubs();return;
    }
    message("Consultando participantes da competição…");
    try{
      const q=new URLSearchParams({campeonato_id:id});
      if(season.value)q.set("temporada",season.value);
      const response=await get("/api/clubes/meta?"+q);
      if(request!==fetchId)return;
      clubs=response.clubes||[];
      setOptions(season,response.temporadas||[],"Escolha a temporada",v=>opt(v,v));
      season.value=response.temporada||"";
      renderClubs();
      feedback.textContent="";
    }catch(e){if(request===fetchId)message(e.message,"error");}
  }
  async function init(){
    try{
      const result=await get("/api/ligas");
      const arr=(result.ligas||[]).filter(x=>x.id);
      setOptions(league,arr,"Escolha o campeonato",r=>opt(r.id,(r.pais?r.pais+" · ":"")+r.nome));
      feedback.textContent="";
      // Link direto de uma partida futura na página de campeonato.
      const preset=new URLSearchParams(location.search);
      const id=preset.get("campeonato_id"),selectedSeason=preset.get("temporada");
      const selectedHome=preset.get("mandante_id"),selectedAway=preset.get("visitante_id");
      if(id&&arr.some(c=>String(c.id)===id)){
        league.value=id;
        if(selectedSeason){
          const meta=await get("/api/clubes/meta?"+new URLSearchParams({
            campeonato_id:id,temporada:selectedSeason
          }));
          clubs=meta.clubes||[];
          setOptions(season,meta.temporadas||[],"Escolha a temporada",v=>opt(v,v));
          season.value=meta.temporada||"";
          renderClubs();
          if(selectedHome&&selectedAway&&selectedHome!==selectedAway&&
            clubs.some(c=>String(c.id)===selectedHome)&&
            clubs.some(c=>String(c.id)===selectedAway)){
            home.value=selectedHome;away.value=selectedAway;
            $("#x1-form").requestSubmit();
          }
        }else{await loadMeta();}
      }
    }catch(e){message(e.message,"error");}
  }
  league.addEventListener("change",()=>{season.value="";loadMeta();});
  season.addEventListener("change",()=>loadMeta());
  home.addEventListener("change",()=>{if(home.value===away.value)away.value="";});
  away.addEventListener("change",()=>{if(home.value===away.value)home.value="";});
  $("#x1-form").addEventListener("submit",async ev=>{
    ev.preventDefault();
    if(!league.value||!season.value||!home.value||!away.value){message("Selecione campeonato, temporada, mandante e visitante.","error");return;}
    if(home.value===away.value){message("Os clubes precisam ser diferentes.","error");return;}
    const params=new URLSearchParams({
      campeonato_id:league.value,temporada:season.value,
      mandante_id:home.value,visitante_id:away.value
    });
    const submit=$(".x1-submit");
    submit.disabled=true;submit.textContent="Calculando probabilidades…";results.hidden=true;
    message("Treinando modelo de gols com as partidas registradas…");
    try{
      const analysisParams=new URLSearchParams(params);
      analysisParams.set("jogos",$("#x1-jogos").value||"20");
      const [predicted,described]=await Promise.allSettled([
        get("/api/apostas/x1?"+params),
        get("/api/apostas/x1/analise?"+analysisParams)
      ]);
      data=predicted.status==="fulfilled"?predicted.value:null;
      if(data)render();
      else {
        $("#x1-headline").innerHTML='<div class="x1-headline-fallback"><strong>'+
          esc(clubs.find(c=>String(c.id)===home.value)?.clube||"Mandante")+
          '</strong> <span>×</span> <strong>'+
          esc(clubs.find(c=>String(c.id)===away.value)?.clube||"Visitante")+'</strong></div>';
      }
      window.X1Dados?.set(described.status==="fulfilled"?described.value:null,
        described.status==="rejected"?described.reason.message:null);
      window.X1Favoritometro?.set(described.status==="fulfilled"?described.value:null,data);
      $("#x1-tabs").querySelectorAll("[data-tab]").forEach(button=>{
        button.disabled=!data&&!["visao","favoritometro"].includes(button.dataset.tab);
        button.title=button.disabled?"Projeção indisponível para esta amostra":"";
      });
      results.hidden=false;
      showTab("visao");
      if(described.status==="rejected"&&predicted.status==="rejected"){
        message("Não foi possível carregar análise e projeção: "+described.reason.message+
          " · "+predicted.reason.message,"error");
      } else if(described.status==="rejected") {
        message("A projeção carregou, mas a análise de dados falhou: "+described.reason.message,"error");
      } else if(predicted.status==="rejected") {
        message("Análise descritiva carregada. Previsão indisponível: "+predicted.reason.message,"error");
      } else {
        feedback.textContent="";
      }
    }catch(e){message(e.message,"error");}
    finally{submit.disabled=false;submit.textContent="Analisar confronto";}
  });
  $("#x1-tabs").addEventListener("click",ev=>{
    const button=ev.target.closest("[data-tab]");
    if(button&&!button.disabled)showTab(button.dataset.tab);
  });
  function showTab(tab){
    $("#x1-tabs").querySelectorAll("[data-tab]").forEach(btn=>{
      const active=btn.dataset.tab===tab;
      btn.classList.toggle("active",active);btn.setAttribute("aria-selected",String(active));
    });
    $("#x1-panels").querySelectorAll("[data-panel]").forEach(el=>el.hidden=el.dataset.panel!==tab);
  }
  function teamTitle(team){
    const icon=team.fotmob_id
      ? '<img src="https://images.fotmob.com/image_resources/logo/teamlogo/'+encodeURIComponent(team.fotmob_id)+'.png" alt="" loading="lazy" onerror="this.style.display=\'none\'">'
      : "";
    return '<div class="x1-team-identity">'+icon+'<div><strong>'+esc(team.clube)+'</strong><small>'+num(team.jogos,0)+' jogos na temporada</small></div></div>';
  }
  function mini(label,p){return '<div class="x1-mini"><span>'+esc(label)+'</span><strong>'+percent(p)+'</strong></div>';}
  function renderVisao(){
    const p=data.probabilidades;
    const lh=data.gols_esperados.mandante,la=data.gols_esperados.visitante;
    $("#x1-headline").innerHTML=teamTitle(data.mandante)+
      '<div class="x1-versus"><span>x1</span><small>'+esc(data.campeonato.nome)+' · '+esc(data.temporada)+'</small></div>'+
      teamTitle(data.visitante);
    $("#x1-visao").innerHTML=
      '<div class="x1-keyrates">'+
       mini(data.mandante.clube+" vence",p.mandante)+mini("Empate",p.empate)+mini(data.visitante.clube+" vence",p.visitante)+
       mini("1X",p.mandante_ou_empate)+mini("X2",p.visitante_ou_empate)+mini("Ambos marcam",p.ambos_marcam)+
      '</div>'+
      '<section class="x1-card"><h2>Gols esperados pelo modelo</h2><div class="x1-expected"><div><span>'+esc(data.mandante.clube)+'</span><strong>'+num(lh)+'</strong></div><span class="x1-divider">×</span><div><span>'+esc(data.visitante.clube)+'</span><strong>'+num(la)+'</strong></div></div>'+
      '<p class="x1-help">Projeção de gols para um confronto hipotético na temporada selecionada. Não representa placar previsto com certeza.</p></section>'+
      renderFisicos()+
      '<section class="x1-card"><h2>Resumo da previsão</h2><p>'+esc(data.relatorio[0])+'</p></section>';
  }
  function renderFisicos(){
    const fis=data.fisicos||{};
    const h=fis.mandante||{},v=fis.visitante||{};
    const cell=(label,key,digits=1)=>
      '<tr><td>'+label+'</td><td>'+num(h[key],digits)+'</td><td>'+num(v[key],digits)+'</td></tr>';
    return '<section class="x1-card"><h2>Indicadores físicos · médias por jogo</h2>'+
      '<p class="x1-help">Fonte: dados_fisicos (SofaScore). Estatísticas históricas, não volume de corrida conhecido antes da próxima partida.</p>'+
      '<div class="table-wrap"><table class="data-table"><thead><tr><th>Indicador</th><th>Mandante</th><th>Visitante</th></tr></thead><tbody>'+
      cell("Distância percorrida (km)","avg_distancia_percorrida",2)+
      cell("Sprints","avg_sprints",1)+
      cell("Jogos com KM","jogos_km",0)+
      cell("Jogos com sprints","jogos_sprints",0)+
      cell("Média KM como mandante","km_casa",2)+
      cell("Média KM como visitante","km_fora",2)+
      cell("Média sprints como mandante","sprints_casa",1)+
      cell("Média sprints como visitante","sprints_fora",1)+
      '</tbody></table></div>'+
      '<p class="x1-help">Ajuste na projeção: '+(fis.aplicado?'aplicado (efeito limitado a 4% sobre gols esperados)':'não aplicado — cobertura física insuficiente')+
      '. A associação entre correr mais e vencer não demonstra causalidade.</p></section>';
  }
  function polar(i,total,r){
    const angle=-Math.PI/2+2*Math.PI*i/total;
    return [205+Math.cos(angle)*r,190+Math.sin(angle)*r];
  }
  function polygon(values,r=120){
    if(!values.every(v=>v!=null&&Number.isFinite(Number(v))))return null;
    return values.map((v,i)=>polar(i,values.length,r*v/100).map(n=>n.toFixed(1)).join(",")).join(" ");
  }
  function radarSVG(labels,valuesA,valuesB){
    const count=labels.length;
    const outline=[.25,.5,.75,1].map(f=>'<polygon points="'+Array.from({length:count},(_,i)=>polar(i,count,120*f).join(",")).join(" ")+'" fill="none" stroke="var(--df-border)" stroke-width="1"/>').join("");
    const axes=labels.map((_,i)=>'<line x1="205" y1="190" x2="'+polar(i,count,120).join('" y2="')+'" stroke="var(--df-border)" />').join("");
    const paths=[valuesA,valuesB].map((arr,i)=>{
      const color=i===0?'#ff7b32':'#52a4ff',pts=polygon(arr);
      if(pts)return '<polygon points="'+pts+'" fill="'+(i===0?'rgba(255,107,26,.16)':'rgba(47,145,231,.14)')+'" stroke="'+color+'" stroke-width="3"/>';
      // Sem dados em algum eixo: desenha somente segmentos válidos, sem simular zero.
      return arr.map((v,j)=>{
        const next=(j+1)%arr.length;
        if(v==null||arr[next]==null)return '';
        return '<line x1="'+polar(j,arr.length,120*v/100)[0]+'" y1="'+polar(j,arr.length,120*v/100)[1]+
          '" x2="'+polar(next,arr.length,120*arr[next]/100)[0]+'" y2="'+polar(next,arr.length,120*arr[next]/100)[1]+
          '" stroke="'+color+'" stroke-width="3" stroke-linecap="round"/>';
      }).join('');
    }).join("");
    const points=[valuesA,valuesB].map((arr,i)=>arr.map((v,j)=>v==null?'':(()=>{
      const [x,y]=polar(j,count,120*v/100);
      return '<circle cx="'+x+'" cy="'+y+'" r="4" fill="'+(i===0?'#ff7b32':'#52a4ff')+'"/>';
    })()).join("")).join("");
    const names=labels.map((name,i)=>{
      const [x,y]=polar(i,count,156);
      return '<text x="'+x+'" y="'+y+'" fill="var(--df-text)" font-size="11" text-anchor="middle" dominant-baseline="middle">'+esc(name)+'</text>';
    }).join("");
    return '<svg viewBox="0 0 410 390" role="img" aria-label="Radar comparativo">'+outline+axes+paths+points+names+'</svg>';
  }
  function radarTable(labels,a,b){
    return '<div class="x1-radar-table"><table><thead><tr><th>Atributo</th><th>Mandante</th><th>Visitante</th></tr></thead><tbody>'+
      labels.map((label,i)=>'<tr><td>'+esc(label)+'</td><td>'+num(a[i],0)+'</td><td>'+num(b[i],0)+'</td></tr>').join("")+'</tbody></table></div>';
  }
  function radarCard(kind,title,description){
    const ar=data.mandante.radar?.[kind],br=data.visitante.radar?.[kind];
    if(!ar||!br)return '<section class="x1-card"><h2>'+title+'</h2><p>Estatísticas insuficientes para calcular este radar.</p></section>';
    const labels=ar.labels,aa=ar.values,bb=br.values;
    return '<article class="x1-card x1-radar-card"><h2>'+esc(title)+'</h2><p class="x1-help">'+esc(description)+'</p>'+
      radarSVG(labels,aa,bb)+radarTable(labels,aa,bb)+'</article>';
  }
  function renderRadar(){
    const names='<div class="x1-legend"><span class="x1-home-dot"></span>'+esc(data.mandante.clube)+
      '<span class="x1-away-dot"></span>'+esc(data.visitante.clube)+'</div>';
    $("#x1-radar").innerHTML=names+'<div class="x1-radars">'+
      radarCard("geral","Desempenho geral","Percentis calculados em relação aos clubes da competição. Notas mais altas representam melhor posição relativa.")+
      radarCard("fundamentos","Forças por fundamento","Jogo aéreo defensivo é aproximado por desempenho em duelos; bola parada defensiva aparece indisponível sem xG sofrido desse tipo.")+
      '</div><p class="x1-help">Notas comparativas de 0 a 100; não são ratings oficiais da EA Sports nem probabilidades de vencer.</p>';
  }
  function percentbar(value){
    return '<div class="x1-bar" role="img" aria-label="'+percent(value)+'"><span style="width:'+Math.max(0,Math.min(100,value*100)).toFixed(1)+'%"></span></div>';
  }
  function renderProbabilidades(){
    const p=data.probabilidades;
    $("#x1-probabilidades").innerHTML=
      '<section class="x1-card"><h2>Resultado e dupla chance</h2><div class="x1-prob-grid">'+[
        ["Mandante",p.mandante],["Empate",p.empate],["Visitante",p.visitante],
        ["Mandante ou empate",p.mandante_ou_empate],["Visitante ou empate",p.visitante_ou_empate]
      ].map(([n,v])=>'<div class="x1-prob"><div><span>'+n+'</span><strong>'+percent(v)+'</strong></div>'+percentbar(v)+'</div>').join("")+'</div></section>'+
      '<section class="x1-card"><h2>Mercados de gols e eventos</h2><div class="x1-prob-grid">'+
      markets.map(([key,name])=>'<div class="x1-prob"><div><span>'+name+'</span><strong>'+percent(p[key])+'</strong></div>'+percentbar(p[key])+'</div>').join("")+'</div>'+
      '<p class="x1-help">Goleada = vitória por 3 ou mais gols. Placar de 1x0 aos 60 minutos = resultado exato no minuto 60, usando a aproximação de gols uniformes no tempo. Over 0,5 HT usa estimativa de 46% da intensidade de gols para o primeiro tempo.</p></section>';
  }
  function renderPlacares(){
    const scores=data.placares;
    const m=Math.max(...scores.filter(s=>s.placar!=="Outro placar").map(s=>s.probabilidade),.001);
    $("#x1-placares").innerHTML='<section class="x1-card"><h2>Mapa de calor de placares</h2>'+
      '<p class="x1-help">A intensidade da cor é proporcional à chance de cada placar entre os resultados listados. “Outro” agrega todas as combinações não exibidas.</p>'+
      '<div class="x1-score-grid">'+scores.map(s=>{
        const weight=s.placar==="Outro placar"?.2:s.probabilidade/m;
        const alpha=(.08+.54*Math.pow(weight,.77)).toFixed(3);
        return '<div class="x1-score" style="--x1-score-strength:'+alpha+'"><strong>'+esc(s.placar)+'</strong><span>'+percent(s.probabilidade)+'</span></div>';
      }).join("")+'</div></section>';
  }
  function oddsRow(key,label,info){
    const p=info.prob_evento;
    const lay=key.startsWith("lay_");
    return '<tr data-x1-odd-row="'+key+'" data-prob="'+p+'" data-lay="'+lay+'">'+
      '<td>'+esc(label)+'</td>'+
      '<td>'+percent(p)+'</td>'+
      '<td>'+num(info.odd_justa,2)+'</td>'+
      '<td>'+(info.limite_odd_ev_3pct==null?'—':(lay?'≤ ':'≥ ')+num(info.limite_odd_ev_3pct,2))+'</td>'+
      '<td><input class="x1-market-quote" type="number" min="1.01" max="1000" step="0.01" inputmode="decimal" placeholder="Ex.: 2.50" aria-label="Odd de '+esc(label)+'"></td>'+
      '<td class="x1-ev-result" aria-live="polite">—</td></tr>';
  }
  function updateEV(row){
    const offered=Number($(".x1-market-quote",row).value);
    const val=$(".x1-ev-result",row);
    if(!Number.isFinite(offered)||offered<1.01){val.textContent="—";val.className="x1-ev-result";return;}
    const p=Number(row.dataset.prob),lay=row.dataset.lay==="true";
    const ev=lay ? (1-p)*(.98)-p*(offered-1) : p*offered-1;
    val.textContent=(ev>=0?"+":"")+(ev*100).toFixed(1).replace(".",",")+"%";
    val.className="x1-ev-result "+(ev>=.03?"x1-positive":ev<0?"x1-negative":"");
  }
  function renderOdds(){
    $("#x1-odds").innerHTML='<section class="x1-card"><h2>Odds justas e análise de valor esperado</h2>'+
      '<p class="x1-help">Odd justa = 1 / probabilidade estimada. Na odd justa, EV ≈ 0 antes de custos. A coluna EV +3% mostra a <strong>odd mínima para back</strong> ou a <strong>odd máxima para lay</strong> para obter EV modelado de +3% sobre a stake. Lay considera comissão ilustrativa de 2% nos ganhos. Sem odds reais, não há sinal de valor identificado.</p>'+
      '<div class="table-wrap"><table class="data-table x1-odds-table"><thead><tr><th>Mercado</th><th>Probabilidade do evento</th><th>Odd justa</th><th>Referência EV +3%</th><th>Odd oferecida</th><th>EV calculado</th></tr></thead><tbody>'+
      oddsNames.map(([k,n])=>oddsRow(k,n,data.odds[k])).join("")+
      '</tbody></table></div>'+
      '<p class="x1-help">Para lay, “probabilidade do evento” é a chance da seleção contra a qual se aposta, não a chance de sucesso do lay. As odds são apenas pontos de partida sujeitos a incerteza e diferenças entre casas.</p></section>';
    $("#x1-odds").querySelectorAll(".x1-market-quote").forEach(input=>input.addEventListener("input",()=>updateEV(input.closest("tr"))));
  }
  function renderReport(){
    const model=data.modelo;
    $("#x1-relatorio").innerHTML='<section class="x1-card"><h2>Relatório de confronto</h2><div class="x1-report">'+
      data.relatorio.slice(0,2).map(p=>'<p>'+esc(p)+'</p>').join("")+
      '</div><div class="x1-model-meta">'+
      '<span>Modelo: '+esc(model.nome)+'</span>'+
      '<span>Jogos de treinamento: '+num(model.amostra_jogos,0)+'</span>'+
      '<span>Temporadas: '+esc((model.temporadas_treino||[]).join(" · "))+'</span>'+
      '<span>Ajuste por xG: '+(model.ajuste_xg?"sim":"não")+'</span></div>'+
      '<p class="x1-help">'+esc(model.aviso)+'</p></section>';
  }
  function render(){
    renderVisao();renderRadar();renderProbabilidades();renderPlacares();renderOdds();renderReport();
  }
  init();
})();