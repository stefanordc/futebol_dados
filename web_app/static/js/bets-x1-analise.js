/* X1 · análise descritiva baseada no recorte escolhido, sem inferências de dados ausentes. */
(() => {
  "use strict";
  const panel=document.querySelector("#x1-visao");
  if(!panel)return;
  const esc=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const num=(n,d=2)=>n==null||!Number.isFinite(Number(n))?"—":
    Number(n).toLocaleString("pt-BR",{minimumFractionDigits:d,maximumFractionDigits:d});
  let analysis=null,category="resumo",mode="avg",error=null;
  const tabs=[
    ["resumo","Resumo e resultados"],["ataque","Ataque e conversão"],
    ["defesa","Defesa"],["criacao","Construção e passes"],
    ["gols","Tipos de gol"],["consistencia","Consistência e jogos"],
    ["fisico","Dados físicos"],["disciplina","Disputas e disciplina"]
  ];
  // [chave,rótulo,tipo,origem,nota]; valores de razão/percentual/variância
  // são invariantes ao controle de média/total.
  const vars={
    resumo:[
      ["jogos","Partidas","fixed"],["vitorias","Vitórias","count"],
      ["empates","Empates","count"],["derrotas","Derrotas","count"],
      ["pontos","Pontos","count"],["aproveitamento_pct","Aproveitamento","pct"],
      ["gols_marcados","Gols marcados","count"],["gols_sofridos","Gols sofridos","count"],
      ["saldo_gols","Saldo de gols","count"],["clean_sheets","Jogos sem sofrer gol","count"],
      ["sem_marcar","Jogos sem marcar","count"],["vitorias_pct","Taxa de vitórias","pct"]
    ],
    ataque:[
      ["total_chutes","Finalizações","count","total_chutes"],
      ["chutes_certos","Finalizações certas","count","chutes_certos"],
      ["chutes_fora","Finalizações para fora","count","chutes_fora"],
      ["chutes_bloqueados","Finalizações bloqueadas","count","chutes_bloqueados"],
      ["chutes_trave","Bolas na trave","count","chutes_trave"],
      ["chutes_dentro_area","Chutes dentro da área","count","chutes_dentro_area"],
      ["chutes_fora_area","Chutes fora da área","count","chutes_fora_area"],
      ["grandes_chances","Grandes chances","count","grandes_chances"],
      ["grandes_chances_perdidas","Grandes chances perdidas","count","grandes_chances_perdidas"],
      ["xg","xG criado","count","xg"],
      ["xgot","xGOT","count","xgot"],
      ["xg_jogada_normal","xG em jogada normal","count","xg_jogada_normal"],
      ["xg_jogada_ensaiada","xG em bola parada","count","xg_jogada_ensaiada"],
      ["xg_sem_penalti","xG sem pênalti","count","xg_sem_penalti"],
      ["chutes_por_gol","Finalizações para marcar 1 gol","ratio","total_chutes"],
      ["chutes_certos_por_gol","Chutes certos para marcar 1 gol","ratio","chutes_certos"],
      ["grandes_chances_por_gol","Grandes chances para marcar 1 gol","ratio","grandes_chances"],
      ["precisao_finalizacoes_pct","Precisão das finalizações","pct","total_chutes"],
      ["conversao_chutes_pct","Conversão de chutes em gol","pct","total_chutes"],
      ["eficiencia_xg_pct","Eficiência de conversão de xG","pct","xg",
        "Gols marcados ÷ xG, usando apenas jogos com xG informado. 100% é igual ao esperado; valores acima de 100% indicam gols acima do esperado."],
      ["gols_menos_xg","Gols acima/abaixo do xG","count","xg",
        "Gols − xG apenas em jogos com xG. Um resultado negativo indica menos gols do que as chances sugeriam."]
    ],
    defesa:[
      ["gols_sofridos","Gols sofridos","count"],
      ["rival_total_chutes","Finalizações concedidas","count","rival_total_chutes"],
      ["rival_chutes_certos","Chutes certos concedidos","count","rival_chutes_certos"],
      ["rival_xg","xG concedido (xGA)","count","rival_xg"],
      ["rival_xgot","xGOT concedido","count","rival_xgot"],
      ["rival_grandes_chances","Grandes chances concedidas","count","rival_grandes_chances"],
      ["rival_chutes_dentro_area","Chutes sofridos na área","count","rival_chutes_dentro_area"],
      ["chutes_sofridos_por_gol","Chutes sofridos por gol concedido","ratio","rival_total_chutes"],
      ["xga_menos_gols_sofridos","xGA − gols sofridos","count","rival_xg",
        "Positivo: sofreu menos gols que o xG concedido. Medida descritiva, influenciada por goleiro, finalização adversária e variabilidade."],
      ["clean_sheets","Jogos sem sofrer gols","count"],
      ["desarmes","Desarmes","count","desarmes"],
      ["interceptacoes","Interceptações","count","interceptacoes"],
      ["bloqueios","Bloqueios defensivos","count","bloqueios"],
      ["bolas_afastadas","Bolas afastadas","count","bolas_afastadas"],
      ["defesas_goleiro","Defesas do goleiro","count","defesas_goleiro"]
    ],
    criacao:[
      ["passes","Passes tentados","count","passes"],
      ["passes_certos","Passes certos","count","passes_certos"],
      ["acerto_passes_pct","Precisão dos passes","pct","passes"],
      ["passes_certos_por_gol","Passes certos para marcar 1 gol","ratio","passes_certos",
        "Passes certos ÷ gols marcados somente nos jogos com passes registrados; associação descritiva, não significa que esses passes causaram o gol."],
      ["posse_bola","Posse de bola média","pctRaw","posse_bola"],
      ["passes_longos","Passes longos","count","passes_longos"],
      ["passes_longos_certos","Passes longos certos","count","passes_longos_certos"],
      ["cruzamentos","Cruzamentos","count","cruzamentos"],
      ["cruzamentos_certos","Cruzamentos certos","count","cruzamentos_certos"],
      ["acerto_cruzamentos_pct","Eficiência dos cruzamentos","pct","cruzamentos"],
      ["toques_area_adversaria","Toques na área adversária","count","toques_area_adversaria"],
      ["escanteios","Escanteios","count","escanteios"],
      ["dribles","Dribles tentados","count","dribles"],
      ["dribles_certos","Dribles certos","count","dribles_certos"],
      ["acerto_dribles_pct","Eficiência de dribles","pct","dribles"]
    ],
    consistencia:[
      ["variancia_saldo","Variância do saldo de gols","variance",null,
        "Variância amostral dos saldos (gols marcados − sofridos) de cada jogo. Mede quanto o saldo oscila em torno da média: quanto maior, menos estável; não mede diretamente a qualidade da equipe. Unidade: gols². É calculada dividindo por n − 1."],
      ["desvio_padrao_saldo","Desvio-padrão do saldo","fixed",null,
        "Raiz quadrada da variância do saldo. Oscilação típica em gols por jogo."],
      ["variancia_gols_marcados","Variância dos gols marcados","variance",null,
        "Variância amostral da quantidade de gols feitos por jogo. Quanto maior, mais irregular é a produção de gols."],
      ["coef_variacao_gols","Coeficiente de variação ofensivo","pct",null,
        "Desvio-padrão de gols dividido pela média de gols do time; pode subir muito quando a média é baixa."],
      ["amplitude_saldo","Amplitude do saldo","fixed",null,
        "Diferença entre o maior e o menor saldo de gols em uma partida da amostra."],
      ["media_pontos","Pontos por partida","fixed"]
    ],
    fisico:[
      ["distancia_percorrida","Distância percorrida (km)","count","distancia_percorrida"],
      ["sprints","Número de sprints","count","sprints"]
    ],
    disciplina:[
      ["disputas_ganhas","Duelos vencidos","count","disputas_ganhas"],
      ["disputas_chao","Duelos pelo chão","count","disputas_chao"],
      ["disputas_chao_ganhas","Duelos pelo chão vencidos","count","disputas_chao_ganhas"],
      ["disputas_aereas","Duelos aéreos","count","disputas_aereas"],
      ["disputas_aereas_ganhas","Duelos aéreos vencidos","count","disputas_aereas_ganhas"],
      ["acerto_aereo_pct","Eficiência aérea","pct","disputas_aereas"],
      ["impedimentos","Impedimentos","count","impedimentos"],
      ["faltas_cometidas","Faltas cometidas","count","faltas_cometidas"],
      ["faltas_recebidas","Faltas recebidas","count","faltas_recebidas"],
      ["cartao_amarelo","Cartões amarelos","count","cartao_amarelo"],
      ["cartao_vermelho","Cartões vermelhos","count","cartao_vermelho"]
    ]
  };
  const types=[
    ["pe_direito","Pé direito"],["pe_esquerdo","Pé esquerdo"],["cabeca","Cabeça"],
    ["bola_parada","Bola parada"],["escanteio","Escanteio"],["falta","Falta"],
    ["penalti","Pênalti"],["individual","Jogada individual"],
    ["contra_ataque","Contra-ataque"],["jogada_normal","Jogada normal"]
  ];
  const coverage=(team,spec)=>{
    const key=spec[3],found=team.cobertura||{};
    return key&&found[key]!=null?Number(found[key]):null;
  };
  function metric(team,spec){
    const [key,,type]=spec;
    let v=team.metricas?.[key];
    if(v==null)return "—";
    const cov=coverage(team,spec);
    if(type==="count"&&mode==="avg"){
      const prescribed=team.metricas?.[key+"_por_jogo"];
      const divisor=cov ?? team.jogos;
      v=prescribed!=null?prescribed:(divisor?Number(v)/divisor:null);
    }
    if(type==="pct"||type==="pctRaw")return num(v,1)+"%";
    if(type==="variance"||type==="ratio")return num(v,2);
    return num(v,mode==="avg"&&type==="count"?2:0);
  }
  function tip(desc){
    return desc?'<details class="x1-tip"><summary aria-label="Como interpretar" title="Como interpretar">?</summary><p>'+esc(desc)+'</p></details>':"";
  }
  function comparisonRows(specs){
    const a=analysis.mandante,b=analysis.visitante;
    return '<div class="x1-compare-table"><table><thead><tr><th>Indicador</th><th>'+esc(a.nome||"Mandante")+'</th><th>'+esc(b.nome||"Visitante")+'</th></tr></thead><tbody>'+
      specs.map(spec=>{
        const ac=coverage(a,spec),bc=coverage(b,spec),show=ac!==null||bc!==null;
        return '<tr><th><div class="x1-metric-name">'+esc(spec[1])+tip(spec[4])+'</div></th>'+
          '<td>'+metric(a,spec)+(show?'<small>'+(ac===null?"":ac+"/"+a.jogos+" jogos")+'</small>':"")+'</td>'+
          '<td>'+metric(b,spec)+(show?'<small>'+(bc===null?"":bc+"/"+b.jogos+" jogos")+'</small>':"")+'</td></tr>';
      }).join("")+'</tbody></table></div>';
  }
  function kpi(team,key,label,d=1){
    let value=team.metricas?.[key];
    const isPercent=key.endsWith("_pct");
    return '<article class="x1-data-kpi"><span>'+esc(label)+'</span><strong>'+(
      value==null?"—":num(value,isPercent?1:d)+(isPercent?"%":""))+'</strong></article>';
  }
  function summary(){
    const a=analysis.mandante,b=analysis.visitante;
    const one=(team)=>'<div class="x1-team-summary"><h3>'+esc(team.nome||"Clube")+'</h3>'+
      '<span class="x1-note">Jogos analisados: '+num(team.jogos,0)+' · '+esc(team.metricas?.forma||"—")+'</span>'+
      '<div class="x1-data-kpis">'+
      kpi(team,"aproveitamento_pct","Aproveitamento")+
      kpi(team,"media_pontos","Pontos/jogo",2)+
      kpi(team,"media_gols_marcados","Gols/jogo",2)+
      kpi(team,"media_gols_sofridos","Gols sofridos/jogo",2)+
      '</div></div>';
    return '<div class="x1-side-by-side">'+one(a)+one(b)+'</div>'+
      '<section class="x1-card"><h2>Comparativo de resultados</h2>'+
      comparisonRows(vars.resumo)+
      '<p class="x1-help">O recorte é aplicado separadamente a cada clube, dentro da competição e temporada escolhidas. A quantidade disponível pode ser menor do que a solicitada.</p></section>';
  }
  function goalTypes(){
    const a=analysis.mandante,b=analysis.visitante;
    const gA=a.tipos_gol||{},gB=b.tipos_gol||{};
    const show=(team,g)=>{
      const events=g?.gols_em_eventos||0,coverage=g?.jogos_com_mapa||0;
      return '<p class="x1-help">'+esc(team.nome||"Clube")+': '+coverage+'/'+team.jogos+
        ' jogos têm mapas; '+events+' gols registrados em eventos. '
        +'As categorias podem se sobrepor (ex.: pênalti de pé direito).</p>';
    };
    return '<section class="x1-card"><h2>Como os clubes marcam seus gols</h2>'+
      show(a,gA)+show(b,gB)+
      '<div class="x1-compare-table"><table><thead><tr><th>Tipo de gol</th><th>'+esc(a.nome||"Mandante")+
      '</th><th>'+esc(b.nome||"Visitante")+'</th></tr></thead><tbody>'+
      types.map(([key,label])=>{
        const cell=(team,g)=>{
          const count=g?.tipos?.[key],maps=g?.jogos_com_mapa||0;
          return count==null?"—":num(mode==="avg"?(maps?count/maps:null):count,mode==="avg"?2:0);
        };
        return '<tr><th>'+esc(label)+'</th><td>'+cell(a,gA)+'</td><td>'+cell(b,gB)+'</td></tr>';
      }).join('')+'</tbody></table></div>'+
      '<p class="x1-help">Média = gols classificados por partida com mapa de finalizações, não por todas as partidas da temporada. Não use a soma dos tipos como total de gols.</p></section>';
  }
  function lineChart(team,idx){
    const list=[...(team.recente||[])].reverse();
    if(!list.length)return '<p class="x1-help">Sem partidas no recorte.</p>';
    const width=640,height=180,padding=27,steps=Math.max(1,list.length-1);
    const max=Math.max(3,...list.map(g=>Math.max(Number(g.gm)||0,Number(g.gs)||0)));
    const xy=(i,v)=>[(padding+(width-2*padding)*i/steps).toFixed(1),
      (height-padding-(height-2*padding)*Number(v)/max).toFixed(1)];
    const series=(key,color)=>'<polyline points="'+list.map((g,i)=>xy(i,g[key]).join(",")).join(" ")+
      '" fill="none" stroke="'+color+'" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'+
      list.map((g,i)=>{const [x,y]=xy(i,g[key]);return '<circle cx="'+x+'" cy="'+y+'" r="3.5" fill="'+color+'"/>';}).join("");
    return '<div class="x1-chart"><h3>'+esc(team.nome||"Clube")+'</h3><svg viewBox="0 0 640 180" role="img" aria-label="Gols marcados e sofridos por partida, em ordem cronológica">'+
      [0,.5,1].map(f=>'<line x1="27" y1="'+(height-padding-f*(height-2*padding))+'" x2="613" y2="'+(height-padding-f*(height-2*padding))+'" stroke="var(--df-border)" stroke-width="1"/>').join("")+
      series("gm","#ff7b32")+series("gs","#52a4ff")+'</svg>'+
      '<p class="x1-help">Laranja: gols feitos · Azul: gols sofridos · Da partida mais antiga à mais recente.</p></div>';
  }
  function matches(){
    const a=analysis.mandante,b=analysis.visitante;
    return '<section class="x1-card"><h2>Dispersão dos resultados</h2>'+
      comparisonRows(vars.consistencia)+
      '<p class="x1-help">Variância menor indica desempenho mais constante no saldo de gols, não necessariamente mais vitórias. Ex.: vencer por 1 a 0 sempre é estável, mas alternar 5 a 0 e 0 a 5 apresenta variância alta.</p></section>'+
      '<section class="x1-card"><h2>Evolução das partidas</h2><div class="x1-side-by-side">'+lineChart(a,0)+lineChart(b,1)+'</div></section>'+
      '<section class="x1-card"><h2>Resultados recentes</h2>'+
      ['mandante','visitante'].map(key=>{
        const team=analysis[key];
        return '<h3>'+esc(team.nome||key)+'</h3><div class="x1-compare-table"><table><thead><tr><th>Data</th><th>Mando</th><th>Placar (clube × rival)</th><th>Pontos</th><th>xG</th><th>Chutes</th></tr></thead><tbody>'+
        (team.recente||[]).map(r=>'<tr><td>'+esc(r.data||"—")+'</td><td>'+esc(r.mando)+'</td><td>'+
        num(r.gm,0)+' × '+num(r.gs,0)+'</td><td>'+num(r.pontos,0)+'</td><td>'+
        num(r.xg,2)+'</td><td>'+num(r.chutes,0)+'</td></tr>').join("")+
        '</tbody></table></div>';
      }).join("")+'</section>';
  }
  function standard(){
    const label=tabs.find(([key])=>key===category)?.[1]||"Comparativo";
    const specs=vars[category]||[];
    let prefix="";
    if(category==="fisico")prefix='<p class="x1-help">KM e sprints provenientes da tabela dados_fisicos; pertencem às partidas do mesmo recorte. Campos ausentes não são estimados.</p>';
    if(category==="ataque")prefix='<p class="x1-help">Conversão xG = gols / xG; 100% indica gols iguais ao esperado. Chutes por gol e passes por gol são razões calculadas somente nos jogos com registro da estatística.</p>';
    return '<section class="x1-card"><h2>'+esc(label)+'</h2>'+prefix+
      comparisonRows(specs)+'</section>';
  }
  function render(){
    if(error){panel.innerHTML='<section class="x1-card"><h2>Análise de dados</h2><p class="x1-message error">'+esc(error)+'</p></section>';return;}
    if(!analysis){panel.innerHTML='<section class="x1-card"><h2>Análise de dados</h2><p class="x1-help">Selecione o campeonato e os dois clubes para comparar os indicadores.</p></section>';return;}
    const n=analysis.recorte==="temporada"?"temporada inteira":"últimos "+analysis.recorte+" jogos";
    panel.innerHTML='<section class="x1-analysis-header"><div><div class="df-eyebrow">ANÁLISE DESCRITIVA</div>'+
      '<h2>Dados e desempenho · '+esc(n)+'</h2><p class="x1-help">Temporada '+esc(analysis.temporada)+
      ' · Cada clube avaliado em seus próprios jogos, no mesmo campeonato.</p></div>'+
      '<div class="x1-view-mode" role="group" aria-label="Apresentação dos dados">'+
      '<button type="button" data-view="avg" aria-pressed="'+(mode==="avg")+'" class="'+(mode==="avg"?"active":"")+'">Média por jogo</button>'+
      '<button type="button" data-view="total" aria-pressed="'+(mode==="total")+'" class="'+(mode==="total"?"active":"")+'">Total</button></div></section>'+
      '<nav class="x1-analysis-tabs" aria-label="Subcategorias da análise">'+
      tabs.map(([key,label])=>'<button type="button" data-analysis-tab="'+key+'" aria-selected="'+(category===key)+'" class="'+(category===key?"active":"")+'">'+esc(label)+'</button>').join("")+'</nav>'+
      '<div id="x1-analysis-content">'+
      (category==="resumo"?summary():category==="gols"?goalTypes():category==="consistencia"?matches():standard())+'</div>'+
      '<p class="x1-disclaimer">Amostras: mandante '+analysis.mandante.jogos+' jogos, visitante '+analysis.visitante.jogos+
      ' jogos. “—” significa dado indisponível ou divisão sem denominador. Percentuais, razões e variâncias não são somados quando o modo muda.</p>';
  }
  panel.addEventListener("click",event=>{
    const group=event.target.closest("[data-analysis-tab]");
    if(group){category=group.dataset.analysisTab;render();return;}
    const view=event.target.closest("[data-view]");
    if(view){mode=view.dataset.view;render();}
  });
  window.X1Dados={
    set(data,err=null){analysis=data||null;error=err;category="resumo";render();},
    render
  };
})();
