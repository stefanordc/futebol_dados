/* Estatísticas adicionais do técnico: usa o recorte de jogos efetivamente comandados. */
(() => {
  "use strict";
  if (!location.pathname.startsWith("/tecnico/")) return;
  const id = Number(location.pathname.split("/")[2]);
  if (!Number.isInteger(id) || id <= 0) return;

  const $ = (q, root=document) => root.querySelector(q);
  const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, c=>({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
  const format = (n,d=0) => n==null || !Number.isFinite(Number(n)) ? "—" :
    Number(n).toLocaleString("pt-BR",{minimumFractionDigits:d,maximumFractionDigits:d});
  const percent=(num,den)=>num!=null&&den>0 ? format(100*num/den,1)+"%" : "—";
  const sum=(items,key)=>{
    const arr=items.map(x=>x[key]).filter(v=>v!=null&&Number.isFinite(Number(v)));
    return arr.length ? arr.reduce((a,v)=>a+Number(v),0) : null;
  };
  const goalTypes=[
    ["pe_direito","Pé direito","corpo"],
    ["pe_esquerdo","Pé esquerdo","corpo"],
    ["cabeca","Cabeça","corpo"],
    ["bola_parada","Bola parada","situacao"],
    ["escanteio","Escanteio","situacao"],
    ["falta","Falta","situacao"],
    ["penalti","Pênalti","situacao"],
    ["individual","Jogada individual","situacao"],
    ["gols_contra_a_favor","Gol contra a favor","registrados"],
  ];
  const tabs=[["resultados","Resultados"],["finalizacoes","Finalizações"],
              ["aereo","Jogo aéreo"],["gols","Tipos de gol"]];
  const cache=new Map();
  let activeTab="resultados";
  let shownKey="";
  let renderSequence=0;
  const season=()=>$("#ent-temp")?.value||"";
  const scoped=records=>{
    const camp=$("#df-profile-camp")?.value||"";
    const club=$("#df-profile-club")?.value||"";
    return (records||[]).filter(r=>
      (!camp||String(r.campeonato_id)===camp)&&(!club||String(r.clube_id)===club));
  };
  const cards=rows=>'<div class="df-coach-kpis">'+rows.map(r=>
    '<article class="df-coach-kpi"><span>'+escapeHtml(r[0])+'</span><strong>'+escapeHtml(r[1])+
    '</strong>'+(r[2]?'<small>'+escapeHtml(r[2])+'</small>':'')+'</article>').join('')+'</div>';
  const table=(rows,columns)=>{
    const head=columns.map(c=>'<th>'+escapeHtml(c[1])+'</th>').join('');
    const body=rows.map(r=>'<tr><td><a href="/liga/'+r.campeonato_id+'">'+escapeHtml(r.campeonato||'—')+
      '</a></td><td><a href="/clube/'+r.clube_id+'">'+escapeHtml(r.clube||'—')+'</a></td>'+
      columns.map(c=>'<td>'+format(r[c[0]],c[2]||0)+'</td>').join('')+'</tr>').join('')||
      '<tr><td colspan="'+(columns.length+2)+'">Sem partidas nos filtros selecionados.</td></tr>';
    return '<div class="table-wrap df-coach-table"><table class="data-table"><thead><tr>'+
      '<th>Campeonato</th><th>Clube</th>'+head+'</tr></thead><tbody>'+body+'</tbody></table></div>';
  };
  function panel(data){
    const rows=scoped(data.linhas||[]);
    const s=k=>sum(rows,k);
    const games=s("jogos");
    const summ=(key)=>{
      const raw=(rows||[]).map(r=>r.gols_tipos||{});
      return sum(raw,key);
    };
    const caption='<p class="df-coach-footnote">'+escapeHtml(data.nota||"")+'</p>';
    const coverage='<p class="df-coach-footnote">Cobertura das estatísticas por equipe: '+
      format(s("partidas_com_estatisticas"))+' de '+format(games)+
      ' jogos. Métricas sem registro aparecem como “—”.</p>';

    if(activeTab==="resultados"){
      const wins=s("vitorias"),draws=s("empates");
      return cards([
        ["Jogos comandados",format(games)],
        ["Vitórias",format(wins)],["Empates",format(draws)],["Derrotas",format(s("derrotas"))],
        ["Aproveitamento",percent(wins==null||draws==null?null:3*wins+draws,3*games)],
        ["Gols feitos",format(s("gols_marcados"))],
        ["Gols sofridos",format(s("gols_sofridos"))],
        ["Clean sheets",format(s("clean_sheets")),"Sem sofrer gols"],
        ["Clean goals",format(s("clean_goals")),"Sem marcar gols"],
        ["% clean sheets",percent(s("clean_sheets"),games)]
      ])+table(rows,[["jogos","J"],["gols_marcados","GM"],["gols_sofridos","GS"],
                     ["clean_sheets","CS"],["clean_goals","CG"]])+caption;
    }
    if(activeTab==="finalizacoes"){
      const shot=s("finalizacoes_feitas"),scored=s("gols_marcados");
      const against=s("finalizacoes_sofridas");
      return cards([
        ["Finalizações realizadas",format(shot)],
        ["Finalizações por jogo",shot!=null&&games?format(shot/games,2):"—"],
        ["No alvo",format(s("finalizacoes_certas"))],
        ["Precisão de chute",percent(s("finalizacoes_certas"),shot)],
        ["Finalizações sofridas",format(against)],
        ["Sofridas por jogo",against!=null&&games?format(against/games,2):"—"],
        ["Conversão de chutes em gols",percent(scored,shot)],
        ["xG produzido",format(s("xg"),2)],["xG sofrido",format(s("xg_sofrido"),2)]
      ])+table(rows,[["jogos","J"],["finalizacoes_feitas","Chutes"],
        ["finalizacoes_certas","No alvo"],["finalizacoes_sofridas","Sofridos"],
        ["finalizacoes_certas_sofridas","Alvo sofrido"],["xg","xG",2],["xg_sofrido","xG sofrido",2]])+
        coverage+caption;
    }
    if(activeTab==="aereo"){
      const attempts=s("duelos_aereos"),won=s("duelos_aereos_ganhos");
      const op=s("duelos_aereos_adversario"),opWon=s("duelos_aereos_adversario_ganhos");
      return cards([
        ["Duelos aéreos disputados",format(attempts)],["Duelos aéreos ganhos",format(won)],
        ["Eficiência aérea",percent(won,attempts)],
        ["Duelos aéreos do adversário",format(op)],
        ["Ganhos pelo adversário",format(opWon)],
        ["Eficiência aérea do adversário",percent(opWon,op)],
        ["xG em bola parada",format(s("xg_bola_parada"),2)]
      ])+table(rows,[["duelos_aereos","Duelos"],["duelos_aereos_ganhos","Ganhos"],
        ["duelos_aereos_adversario","Rival disputas"],["duelos_aereos_adversario_ganhos","Rival ganhos"]])+
      '<p class="df-coach-footnote">Eficiência aérea = disputas aéreas ganhas ÷ disputadas. Esses campos não distinguem automaticamente disputas defensivas e ofensivas.</p>'+coverage;
    }
    const recorded=summ("gols_registrados");
    const withBody=summ("gols_com_tipo_finalizacao");
    const withSituation=summ("gols_com_situacao");
    const entries=goalTypes.map(([key,name,kind])=>{
      const available=kind==="corpo"?withBody:kind==="situacao"?withSituation:recorded;
      const v=summ(key);
      return {key,name,n:available>0?v:null};
    });
    const max=Math.max(1,...entries.map(e=>e.n||0));
    return cards([
      ["Gols na súmula",format(s("gols_marcados"))],
      ["Gols registrados em eventos",format(recorded)],
      ["Gols com parte do corpo",format(withBody)],
      ["Gols com situação de jogada",format(withSituation)]
    ])+'<div class="df-coach-goal-grid">'+entries.map(entry=>
      '<article class="df-coach-goal-card"><div><span>'+escapeHtml(entry.name)+'</span><strong>'+
      format(entry.n)+'</strong></div><div class="df-coach-goal-track"><span style="width:'+
      (entry.n==null?0:Math.round(100*entry.n/max))+'%"></span></div><small>'+
      (entry.n==null?'Sem classificação suficiente':recorded>0?percent(entry.n,recorded)+' dos gols registrados':'Sem eventos de gol')+
      '</small></article>'
    ).join('')+'</div>'+
    '<p class="df-coach-footnote">As categorias podem se sobrepor (ex.: pênalti convertido de pé direito). A ausência de registros não é classificada como zero.</p>'+caption;
  }
  function isStatsActive(){
    const el=$('#df-entity-tabs [data-entity-tab].active');
    return Boolean(el&&el.dataset.entityTab==='estatisticas');
  }
  function ensure(){
    const root=$("#conteudo");
    if(!root||!isStatsActive()||!season())return;
    let mount=$("#df-coach-advanced",root);
    if(mount)return;
    mount=document.createElement("section");
    mount.id="df-coach-advanced";
    mount.className="section df-coach-extra";
    root.append(mount);
    mount.addEventListener("click",event=>{
      const button=event.target.closest("[data-coach-group]");
      if(button){activeTab=button.dataset.coachGroup;paint(mount);return;}
      if(event.target.closest("#df-coach-retry")){cache.delete(season());paint(mount);}
    });
    paint(mount);
  }
  function paint(mount){
    if(!mount?.isConnected)return;
    const seq=++renderSequence,current=season();
    shownKey=current;
    const nav='<nav class="df-coach-nav" aria-label="Subcategorias de estatísticas do técnico">'+
      tabs.map(([key,label])=>'<button type="button" class="tab '+(key===activeTab?'active':'')+
        '" data-coach-group="'+key+'" aria-pressed="'+(key===activeTab)+'">'+label+'</button>').join('')+'</nav>';
    mount.innerHTML='<h2 class="section-title">Análise avançada do técnico</h2>'+nav+
      '<div id="df-coach-detail"><div class="df-coach-loading" role="status">Carregando estatísticas da temporada…</div></div>';
    if(!cache.has(current)){
      const q='/api/tecnico/'+id+'/estatisticas-avancadas?temporada='+encodeURIComponent(current);
      const promise=fetch(q).then(async response=>{
        if(!response.ok){
          let message='HTTP '+response.status;
          try{const json=await response.json();message=json.detail||message;}catch{}
          throw Error(typeof message==='string'?message:'Falha na consulta');
        }
        return response.json();
      });
      cache.set(current,promise);
    }
    cache.get(current).then(data=>{
      if(!mount.isConnected||current!==shownKey||seq!==renderSequence)return;
      $("#df-coach-detail",mount).innerHTML=panel(data);
    }).catch(error=>{
      if(!mount.isConnected||current!==shownKey||seq!==renderSequence)return;
      cache.delete(current);
      $("#df-coach-detail",mount).innerHTML='<div class="error">Não foi possível carregar os indicadores: '+
        escapeHtml(error.message)+' <button type="button" id="df-coach-retry">Tentar novamente</button></div>';
    });
  }
  const main=$("#conteudo");
  if(!main)return;
  new MutationObserver(()=>ensure()).observe(main,{childList:true,subtree:true});
  ensure();
})();