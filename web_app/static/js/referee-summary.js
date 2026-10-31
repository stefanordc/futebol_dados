/** Consulta resumo de arbitragem por campeonato através das APIs já existentes. */
(() => {
  if (!location.pathname.startsWith('/arbitro/')) return;
  const refereeId=Number(location.pathname.split('/').filter(Boolean)[1]);
  if (!Number.isInteger(refereeId))return;
  const signatures=new WeakMap();let request=0;
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num=v=>v==null?'—':Number(v).toLocaleString('pt-BR',{maximumFractionDigits:0});
  async function get(u){const r=await fetch(u);if(!r.ok)throw Error('HTTP '+r.status);return r.json();}
  async function run(key,tbody){
    const token=++request;
    try{
      const qs=new URLSearchParams();if(key)qs.set('temporada',key);
      const meta=await get('/api/stats/meta?'+qs);
      const ligas=(meta.ligas||[]).slice(0,50);
      const matches=[];let i=0,fail=0;
      await Promise.all(Array.from({length:Math.min(5,ligas.length)},async()=>{
        while(i<ligas.length){const liga=ligas[i++];
          try{const q=new URLSearchParams(qs);q.set('campeonato_id',liga.id);
            const result=await get('/api/stats/arbitros?'+q);
            const row=(result.itens||[]).find(r=>Number(r.id)===refereeId);
            if(row&&Number(row.jogos)>0)matches.push({campeonato_id:liga.id,campeonato:liga.nome,...row});
          }catch(e){fail++;}
        }
      }));
      if(token!==request||!tbody.isConnected)return;
      matches.sort((a,b)=>Number(b.jogos||0)-Number(a.jogos||0));
      const table=tbody.closest('table');
      table.querySelector('thead').innerHTML='<tr><th>Campeonato</th><th>J</th><th>Faltas</th><th>Amarelos</th><th>Vermelhos</th><th>Faltas/J</th><th>Amarelos/J</th><th>Vermelhos/J</th></tr>';
      tbody.innerHTML=matches.map(r=>`<tr><td><a href="/liga/${r.campeonato_id}">${esc(r.campeonato)}</a></td><td>${num(r.jogos)}</td><td>${num(r.faltas)}</td><td>${num(r.amarelos)}</td><td>${num(r.vermelhos)}</td><td>${r.faltas_por_jogo??'—'}</td><td>${r.amarelos_por_jogo??'—'}</td><td>${r.vermelhos_por_jogo??'—'}</td></tr>`).join('')||'<tr><td colspan="8">Nenhum campeonato encontrado no período consultado.</td></tr>';
      if(fail){const p=document.createElement('p');p.className='muted';p.textContent=`${fail} consultas de campeonato falharam; dados possivelmente incompletos.`;table.after(p);}
    }catch(e){if(token===request&&tbody.isConnected)tbody.innerHTML=`<tr><td colspan="6">Falha no carregamento: ${esc(e.message)}</td></tr>`;}
  }
  function scan(){
    const root=document.getElementById('conteudo');if(!root)return;
    const selected=document.querySelector('#df-entity-tabs [data-entity-tab="geral"].active');
    if(!selected)return;
    const table=root.querySelector('.section .data-table');
    const tbody=table?.tBodies?.[0];if(!tbody)return;
    const season=document.querySelector('#ent-temp')?.value||'';
    if(signatures.get(tbody)===season)return;
    signatures.set(tbody,season);
    tbody.innerHTML='<tr><td colspan="6">Buscando estatísticas por campeonato…</td></tr>';
    run(season,tbody);
  }
  let scheduled=false;
  const observer=new MutationObserver(()=>{if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;scan();});});
  observer.observe(document.documentElement,{childList:true,subtree:true});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',scan);
  else scan();
})();