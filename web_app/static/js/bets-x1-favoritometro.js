/* Favoritômetro x1: índice relativo explicável, separado das probabilidades 1X2. */
(() => {
  "use strict";
  const root=document.getElementById("x1-favoritometro");
  if(!root)return;
  const esc=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const num=(v,d=1)=>Number(v).toLocaleString("pt-BR",{minimumFractionDigits:d,maximumFractionDigits:d});
  const val=x=>x!=null&&Number.isFinite(Number(x))?Number(x):null;
  const clamp=(x,a=-1,b=1)=>Math.max(a,Math.min(b,x));
  const perc=x=>num(x*100,1)+"%";
  const metric=(t,k)=>val(t?.metricas?.[k]);
  const split=(team,mando)=>{
    const rows=(team?.recente||[]).filter(g=>g.mando===mando);
    return rows.length>=3?{games:rows.length,ppg:rows.reduce((a,x)=>a+Number(x.pontos||0),0)/rows.length}:null;
  };
  let state=null,generated="",loading=false,requestNumber=0;
  function compute(a,p){
    if(!a)return null;
    const h=a.mandante||{},v=a.visitante||{},n=Math.min(h.jogos||0,v.jogos||0);
    const pr=p?.probabilidades||{},ph=val(pr.mandante),pd=val(pr.empate),pv=val(pr.visitante);
    const signals=[],add=(name,raw,weight,detail)=>{if(raw!=null&&Number.isFinite(raw))
      signals.push({name,delta:clamp(raw),weight,detail});};
    if(ph!=null&&pv!=null&&ph+pv>0)
      add("Modelo x1",(ph-pv)/(ph+pv),.65,"Força técnica, defesa e mando considerados no modelo Poisson");
    const mp=metric(h,"media_pontos"),vp=metric(v,"media_pontos");
    if(n>=3&&mp!=null&&vp!=null)
      add("Pontos por jogo",(mp-vp)/3,.15,num(mp,2)+" × "+num(vp,2)+" pontos/jogo");
    const gf=metric(h,"media_gols_marcados"),ga=metric(h,"media_gols_sofridos");
    const vf=metric(v,"media_gols_marcados"),va=metric(v,"media_gols_sofridos");
    if(n>=3&&[gf,ga,vf,va].every(x=>x!=null))
      add("Saldo de gols",((gf-ga)-(vf-va))/2.5,.10,num(gf-ga,2)+" × "+num(vf-va,2)+" saldo/jogo");
    const keys=["xg","rival_xg"];
    const covered=t=>keys.every(k=>(t.cobertura?.[k]||0)>=Math.max(3,Math.ceil((t.jogos||0)*.6)));
    const xgh=metric(h,"xg_por_jogo"),xah=metric(h,"rival_xg_por_jogo");
    const xgv=metric(v,"xg_por_jogo"),xav=metric(v,"rival_xg_por_jogo");
    if(n>=3&&covered(h)&&covered(v)&&[xgh,xah,xgv,xav].every(x=>x!=null))
      add("Saldo de xG",((xgh-xah)-(xgv-xav))/2.5,.05,num(xgh-xah,2)+" × "+num(xgv-xav,2)+" xG−xGA/jogo");
    const local=split(h,"Casa"),road=split(v,"Fora");
    if(local&&road)
      add("Desempenho pelo mando",(local.ppg-road.ppg)/3,.05,
        num(local.ppg,2)+" pontos/jogo como mandante ("+local.games+" jogos) × "+num(road.ppg,2)+" como visitante ("+road.games+" jogos)");
    if(!signals.length)return null;
    const model=ph!=null&&pv!=null&&ph+pv>0;
    const shrink=clamp(n/20,0,1);
    signals.forEach(s=>s.realWeight=model&&s.name!=="Modelo x1"?s.weight*shrink:s.weight);
    const total=signals.reduce((sum,s)=>sum+s.realWeight,0);
    const diff=signals.reduce((sum,s)=>sum+s.delta*s.realWeight,0)/total;
    const home=Math.round(clamp(50+50*diff,0,100)*10)/10,away=Number((100-home).toFixed(1));
    const lead=home>53?"mandante":home<47?"visitante":"equilibrado";
    return {
      home,away,lead,n,signals,drivers:[...signals].sort((a,b)=>Math.abs(b.delta*b.realWeight)-Math.abs(a.delta*a.realWeight)),
      model,prob:ph!=null&&pd!=null&&pv!=null?{home:ph,draw:pd,away:pv}:null,
      hName:p?.mandante?.clube||h.nome||"Mandante",vName:p?.visitante?.clube||v.nome||"Visitante",
      recorte:a.recorte,temporada:a.temporada,
      logos:{mandante:p?.mandante?.fotmob_id||null,visitante:p?.visitante?.fotmob_id||null},
      uncertainty:n<5?"Amostra muito pequena.":n<10?"Amostra curta.":"Amostra histórica; não existe validação externa de calibração do índice."
    };
  }
  function why(r){
    const winner=r.lead==="equilibrado"?null:r.lead==="mandante"?r.hName:r.vName;
    const head=winner?winner+" apresenta vantagem no índice relativo ("+num(Math.max(r.home,r.away))+"% contra "+num(Math.min(r.home,r.away))+"%).":
      "O Favoritômetro aponta confronto equilibrado ("+num(r.home)+"% × "+num(r.away)+"%).";
    const reasons=r.drivers.filter(x=>Math.abs(x.delta)>.025).slice(0,3)
      .map(x=>x.name.toLowerCase()+": "+x.detail);
    const detail=reasons.length?" Indicadores determinantes: "+reasons.join("; ")+".":" Os indicadores disponíveis são próximos.";
    const forecast=r.prob?" Separadamente, o modelo Poisson projeta "+perc(r.prob.home)+" de vitória do mandante, "+
      perc(r.prob.draw)+" de empate e "+perc(r.prob.away)+" de vitória do visitante.":" O modelo de probabilidade 1X2 está indisponível.";
    return [head+detail,"Os sinais descritivos usam "+(r.recorte==="temporada"?"a temporada inteira":r.recorte+" jogos por clube")+
      ", com a força do mando quando há pelo menos três partidas comparáveis. "+r.uncertainty+forecast+
      " O índice não é probabilidade de vitória, nem recomendação de aposta."];
  }
  function id(name,css){
    const initial=String(name).trim().split(/\s+/).slice(0,2).map(x=>x[0]||"").join("").toUpperCase();
    const logo=state?.logos?.[css];
    const content=logo?'<img src="https://images.fotmob.com/image_resources/logo/teamlogo/'+encodeURIComponent(logo)+'.png" alt="" loading="lazy" onerror="this.remove()">':esc(initial);
    return '<span class="x1-fav-monogram '+css+'" aria-hidden="true">'+content+'</span><strong>'+esc(name)+'</strong>';
  }
  function render(){
    if(!state){root.innerHTML='<section class="x1-card"><h2>Favoritômetro</h2><p>Sem indicadores suficientes para calcular o índice.</p></section>';return;}
    const r=state,ex=why(r),weights=r.signals.reduce((sum,s)=>sum+s.realWeight,0);
    root.innerHTML='<section class="x1-fav-hero">'+
      '<div class="df-eyebrow">DADOS FUTEBOL · FAVORITÔMETRO</div><h2>Quem chega mais forte?</h2>'+
      '<p class="x1-help">Índice de força relativa, combinando histórico e projeção disponível. Não confundir com probabilidade de vitória.</p>'+
      '<div class="x1-fav-row">'+
        '<div class="x1-fav-team">'+id(r.hName,"mandante")+'<span class="x1-fav-percent">'+num(r.home)+'%</span><small>MANDANTE</small></div>'+
        '<div class="x1-fav-center"><div class="x1-fav-super">FORÇA RELATIVA</div>'+
        '<div class="x1-fav-bar" role="img" aria-label="'+esc(r.hName)+" "+num(r.home)+"%, "+esc(r.vName)+" "+num(r.away)+'% do índice relativo">'+
        '<span class="x1-fav-bar-home" style="width:'+r.home+'%"></span>'+
        '<span class="x1-fav-bar-away" style="width:'+r.away+'%"></span></div>'+
        '<strong class="x1-fav-x">X1</strong></div>'+
        '<div class="x1-fav-team">'+id(r.vName,"visitante")+'<span class="x1-fav-percent">'+num(r.away)+'%</span><small>VISITANTE</small></div>'+
      '</div><div class="x1-fav-winner">'+(r.lead==="equilibrado"?"Confronto equilibrado":esc(r.lead==="mandante"?r.hName:r.vName)+" lidera o índice")+'</div>'+
      '<p class="x1-help">O gráfico divide 100% entre dois clubes e não representa probabilidades mutuamente exclusivas de vitória: o empate é apresentado separadamente.</p></section>'+
      (r.prob?'<section class="x1-card"><h2>Probabilidades reais do modelo 1X2</h2><div class="x1-fav-probs">'+
        [["Mandante",r.prob.home],["Empate",r.prob.draw],["Visitante",r.prob.away]].map(([name,x])=>
          '<div><small>'+name+'</small><strong>'+perc(x)+'</strong></div>').join("")+'</div>'+
        '<p class="x1-help">São estimativas do modelo Poisson da aplicação, sem garantia de calibração externa. Diferentes do índice visual.</p></section>':"")+
      '<section class="x1-card"><h2>Evidências utilizadas</h2><div class="x1-fav-factors">'+
        r.drivers.map(s=>'<div class="x1-fav-factor"><div><strong>'+esc(s.name)+'</strong><small>'+esc(s.detail)+'</small></div>'+
          '<div class="x1-fav-factor-track"><span style="left:'+(50+50*s.delta)+'%"></span></div>'+
          '<span>'+num(100*s.realWeight/weights,0)+'% do peso</span></div>').join("")+
      '</div></section>'+
      '<section class="x1-card"><div class="x1-fav-report-title"><h2>Justificativa do favoritismo</h2>'+
      '<button type="button" class="x1-fav-ai-btn" '+(loading?"disabled":"")+'>'+(loading?"Gerando…":"Gerar justificativa com IA")+'</button></div>'+
      '<div class="x1-report"><p>'+esc(generated||ex[0])+'</p>'+(generated?"":'<p>'+esc(ex[1])+'</p>')+'</div>'+
      '<p class="x1-help">'+(generated?"Texto produzido por modelo de linguagem; pode conter erros.":"Análise textual automática baseada nos números. IA generativa disponível quando configurada no servidor.")+'</p>'+
      '<p id="x1-fav-ai-info" aria-live="polite" class="x1-help"></p></section>'+
      '<section class="x1-card"><h2>Como o índice é construído</h2><p class="x1-help">'+
      'Modelo Poisson (peso-base 65%, incluindo força técnica e mando), pontos por jogo (15%), saldo de gols (10%), '+
      'saldo de xG (5%) e desempenho em casa/fora (5%). Pesos são redistribuídos quando não há dados suficientes; '+
      'as evidências recentes perdem influência quando a amostra tem menos de 20 partidas. '+
      'É um índice heurístico, não validado como probabilidade de vitória. O efeito específico do mando tem peso pequeno porque o Poisson já considera a vantagem de casa.</p></section>';
  }
  async function generate(){
    if(!state||loading)return;
    const id=++requestNumber;loading=true;render();
    const r=state,weightSum=r.signals.reduce((sum,s)=>sum+s.realWeight,0);
    const payload={
      campeonato:document.getElementById("x1-campeonato")?.selectedOptions?.[0]?.text||"",
      temporada:r.temporada,recorte:String(r.recorte),mandante:r.hName,visitante:r.vName,
      indice_mandante:r.home,indice_visitante:r.away,prob_1x2:r.prob,
      sinais:r.drivers.slice(0,5).map(s=>({nome:s.name,descricao:s.detail,peso_pct:Math.round(100*s.realWeight/weightSum)}))
    };
    try{
      const response=await fetch("/api/apostas/x1/favoritometro/texto",{
        method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)
      });
      const parsed=await response.json();
      if(!response.ok)throw new Error(parsed.detail||"Serviço indisponível.");
      if(id!==requestNumber)return;
      generated=String(parsed.texto||"").slice(0,1800);
    }catch(error){
      if(id!==requestNumber)return;
      loading=false;render();
      const el=document.getElementById("x1-fav-ai-info");
      if(el)el.textContent="IA indisponível: "+error.message+" A explicação automática continua visível.";
      return;
    }
    loading=false;render();
  }
  root.addEventListener("click",e=>{if(e.target.closest(".x1-fav-ai-btn"))generate();});
  window.X1Favoritometro={
    set(a,p){requestNumber++;loading=false;generated="";state=compute(a,p);render();},
    compute,render,why
  };
})();
