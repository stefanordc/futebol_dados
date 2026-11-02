/* Integrações administrativas do Dados Futebol. Não grava chaves de API. */
(() => {
 "use strict";
 const $=(q,base=document)=>base.querySelector(q);
 const $$=(q,base=document)=>Array.from(base.querySelectorAll(q));
 const show=(message,error=false)=>{
   const box=$("#int-message");
   if(box){box.textContent=message;box.className="int-message "+(error?"error":"ok");}
 };
 async function request(url,options={}){
   const r=await fetch(url,{cache:"no-store",...options});
   const result=await r.json().catch(()=>({detail:"Resposta inválida do servidor."}));
   if(!r.ok)throw Error(typeof result.detail==="string"?result.detail:"Falha na operação.");
   return result;
 }
 const json=(body)=>({method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
 const element=(tag,text="",cls="")=>{let el=document.createElement(tag);el.textContent=String(text??"");if(cls)el.className=cls;return el;};
 const opt=(val,name)=>{const e=element("option",name);e.value=String(val);return e;};
 if(location.pathname==="/vincular-clubes"){
   let source="fisicos",result=null;
   async function load(){
     $("#int-link-info").textContent="Consultando banco…";
     try{
       result=await request("/api/integracoes/vinculos?fonte="+source);
       $("#int-link-title").textContent=source==="fisicos"?"Dados físicos · Clubes sem vínculo":source==="api"?"API de odds · Clubes sem vínculo":"Dados físicos · Vincular com clubes sem nenhuma referência";
       $("#int-link-info").textContent=result.total+" pendências · "+result.ja_equivalentes_por_nome+
          " identificados por nome idêntico · "+result.clubes.length+" clubes elegíveis para vínculo.";
       render();
     }catch(e){show(e.message,true);$("#int-link-info").textContent="Não foi possível carregar.";}
   }
   function render(){
     const q=$("#int-link-search").value.trim().toLocaleLowerCase("pt-BR");
     const tbody=$("#int-link-rows");tbody.replaceChildren();
     const matches=(result?.pendentes||[]).filter(s=>s.nome.toLowerCase().includes(q));
     if(!matches.length){
       const row=element("tr"),td=element("td","Não há clubes pendentes para este filtro.");td.colSpan=4;row.append(td);tbody.append(row);return;
     }
     for(const src of matches){
       const tr=element("tr");tr.dataset.id=src.externo_id;
       tr.append(element("td",src.nome),element("td",src.registros));
       const td=document.createElement("td"),select=document.createElement("select");
       select.className="int-link-select";select.setAttribute("aria-label","Vincular "+src.nome);
       select.append(opt("","Não vincular"));
       for(const c of result.clubes)select.append(opt(c.id,c.clube));
       const suggested=src.sugestoes?.find(item=>item.similaridade>=65);
       if(suggested)select.value=String(suggested.id);
       td.append(select);
       if(src.sugestoes?.length)td.append(element("small","Sugestões: "+src.sugestoes.map(x=>x.clube+" ("+x.similaridade+"%)").join(" · "),"int-muted"));
       tr.append(td);
       const last=document.createElement("td"),cb=document.createElement("input");
       cb.type="checkbox";cb.className="int-link-check";cb.setAttribute("aria-label","Selecionar "+src.nome);
       last.append(cb);tr.append(last);tbody.append(tr);
     }
   }
   $$("[data-source]").forEach(btn=>btn.addEventListener("click",()=>{
     source=btn.dataset.source;$$("[data-source]").forEach(b=>b.classList.toggle("int-active",b===btn));$("#int-link-search").value="";load();
   }));
   $("#int-link-search").addEventListener("input",render);
   $("#int-link-save").addEventListener("click",async ()=>{
     const selected=$$("#int-link-rows tr").filter(tr=>$(".int-link-check",tr)?.checked)
       .map(tr=>({externo_id:tr.dataset.id,clube_id:Number($(".int-link-select",tr)?.value)}));
     if(!selected.length||selected.some(x=>!x.clube_id)){show("Marque um clube e escolha a correspondência para cada linha.",true);return;}
     if(!confirm("Registrar "+selected.length+" vínculo(s) em clubes_fontes?"))return;
     const button=$("#int-link-save");button.disabled=true;
     try{const r=await request("/api/integracoes/vinculos",json({fonte:source,vinculos:selected}));
         show(r.vinculados+" vínculo(s) gravado(s) no Supabase.");await load();}
     catch(e){show(e.message,true);}
     finally{button.disabled=false;}
   });
   load();return;
 }
 if(location.pathname!=="/apostas/nostradamus/conectar-api")return;
 let data=null;
 async function history(){
   try{
     const rows=await request("/api/integracoes/odds/importacoes");
     const wrap=$("#int-import-history");wrap.replaceChildren();
     if(!rows.length){wrap.textContent="Nenhuma importação registrada.";return;}
     const table=element("table");table.className="int-table";
     const thead=document.createElement("thead"),head=document.createElement("tr");
     ["ID","Origem","Campeonato","Temporada","Registros","Criado em"].forEach(x=>head.append(element("th",x)));
     thead.append(head);table.append(thead);const body=document.createElement("tbody");
     for(const r of rows){
       const tr=document.createElement("tr");
       [r.id,r.origem,r.campeonato,r.temporada,r.total_registros,
        new Date(r.criado_em).toLocaleString("pt-BR")].forEach(v=>tr.append(element("td",v??"—")));
       body.append(tr);
     }
     table.append(body);wrap.append(table);
   }catch(e){show(e.message,true);}
 }
 function optionSelector(club,options){
   const select=document.createElement("select");select.className="int-odds-club-id";
   select.setAttribute("aria-label","Vincular "+club.original+" ao cadastro");
   select.append(opt("","Sem vínculo no cadastro"));
   for(const c of options)select.append(opt(c.id,c.clube));
   select.value=club.clube_id==null?"":String(club.clube_id);
   return select;
 }
 function renderPreview(){
   $("#int-api-preview").hidden=false;
   $("#int-api-count").textContent=data.total+" registros retornados; fonte não importada ainda.";
   $("#int-season").value=data.temporada||"";
   $("#int-league").value=data.campeonato||"";
   $("#int-country").value=data.pais||"";
   const body=$("#int-api-clubs");body.replaceChildren();
   for(const c of data.clubes){
     const tr=element("tr");tr.dataset.original=c.original;
     const name=element("td",c.original),edit=document.createElement("td");
     const input=document.createElement("input");input.className="int-standard";input.value=c.padronizado;input.maxLength=150;
     edit.append(input);const ref=document.createElement("td"),select=optionSelector(c,data.catalogo);
     select.addEventListener("change",()=>{
       const chosen=data.catalogo.find(x=>String(x.id)===select.value);
       if(chosen)input.value=chosen.clube;
     });
     ref.append(select);
     if(c.sugestoes?.length){
       const hint=element("small","Mais próximos: "+c.sugestoes.map(x=>x.clube+" ("+x.similaridade+"%)").join(" · "),"int-muted");
       ref.append(hint);
     }
     tr.append(name,edit,ref);body.append(tr);
   }
   const cols=$("#int-api-columns");cols.replaceChildren();
   for(const c of data.colunas){
     const label=element("label"),checkbox=document.createElement("input");checkbox.type="checkbox";checkbox.checked=true;checkbox.value=c;
     label.append(checkbox,document.createTextNode(" "+c));cols.append(label);
   }
   $("#int-api-example").textContent=JSON.stringify(data.exemplo,null,2);
 }
 $("#int-api-form").addEventListener("submit",async event=>{
   event.preventDefault();data=null;$("#int-api-preview").hidden=true;
   const submit=$("#int-api-form button[type=submit]");submit.disabled=true;
   try{
     const result=await request("/api/integracoes/odds/preview",json({
       base:$("#int-api-base").value,caminho:$("#int-api-path").value,
       chave:$("#int-api-key").value,cabecalho:$("#int-api-header").value
     }));
     $("#int-api-key").value="";data=result;
     renderPreview();show("Prévia recebida. Revise os clubes e colunas antes de confirmar.");
   }catch(e){show(e.message,true);}
   finally{submit.disabled=false;}
 });
 $("#int-import").addEventListener("click",async()=>{
   if(!data)return;
   const columns=$$("#int-api-columns input:checked").map(x=>x.value);
   if(!columns.length){show("Escolha ao menos uma coluna.",true);return;}
   const clubs=$$("#int-api-clubs tr").map(tr=>({
     original:tr.dataset.original,padronizado:$(".int-standard",tr).value,
     clube_id:$(".int-odds-club-id",tr).value?Number($(".int-odds-club-id",tr).value):null
   }));
   if(!confirm("Importar "+data.total+" registros de odds com "+columns.length+" coluna(s) selecionada(s)?"))return;
   const btn=$("#int-import");btn.disabled=true;
   try{
     const result=await request("/api/integracoes/odds/importar",json({
       preview_id:data.preview_id,colunas:columns,clubes:clubs,
       temporada:$("#int-season").value,campeonato:$("#int-league").value,pais:$("#int-country").value
     }));
     show("Importação #"+result.importacao_id+" concluída: "+result.inseridos+" registros gravados.");
     data=null;$("#int-api-preview").hidden=true;await history();
   }catch(e){show(e.message,true);}
   finally{btn.disabled=false;}
 });
 history();
})();
