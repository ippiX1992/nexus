"use client";
import{FormEvent,useEffect,useState}from"react";
import{AdminShell}from"@/components/admin/AdminShell";
import{Option,OptionValue,catalogCommand,catalogContext,catalogCreate,catalogGet,catalogPage,technicalError}from"@/lib/catalog";

export default function Page(){
 const[items,setItems]=useState<Option[]>([]),[permissions,setPermissions]=useState<string[]>([]),[error,setError]=useState(""),[loading,setLoading]=useState(true);
 const[expanded,setExpanded]=useState<string|null>(null),[values,setValues]=useState<OptionValue[]>([]);
 const canManage=permissions.includes("catalog.option.create")||permissions.includes("catalog.option.update");
 const canManageValues=permissions.includes("catalog.option_value.create");

 async function load(){
  setLoading(true);
  try{
   const[page,ctx]=await Promise.all([catalogPage<Option>("/options"),catalogContext()]);
   setItems(page.items);setPermissions(ctx.permissions);setError("");
  }catch(e){setError(technicalError(e))}finally{setLoading(false)}
 }
 useEffect(()=>{load()},[]);

 async function submit(event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  const formElement=event.currentTarget,form=new FormData(formElement);
  try{
   await catalogCreate("/options",{code:form.get("code"),name:form.get("name"),input_type:form.get("input_type")||"select"});
   formElement.reset();await load();
  }catch(e){setError(technicalError(e))}
 }

 async function archive(item:Option){
  try{await catalogCommand(`/options/${item.id}/archive`,item.version);await load()}
  catch(e){setError(technicalError(e))}
 }

 async function toggleValues(option:Option){
  if(expanded===option.id){setExpanded(null);return}
  try{
   const list=await catalogGet<OptionValue[]>(`/options/${option.id}/values`);
   setValues(list);setExpanded(option.id);
  }catch(e){setError(technicalError(e))}
 }

 async function submitValue(optionId:string,event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  const formElement=event.currentTarget,form=new FormData(formElement);
  try{
   await catalogCreate(`/options/${optionId}/values`,{code:form.get("code"),value:form.get("value"),swatch_hex:form.get("swatch_hex")||undefined});
   formElement.reset();
   const list=await catalogGet<OptionValue[]>(`/options/${optionId}/values`);
   setValues(list);
  }catch(e){setError(technicalError(e))}
 }

 async function archiveValue(optionId:string,value:OptionValue){
  try{
   await catalogCommand(`/option-values/${value.id}/archive`,value.version);
   const list=await catalogGet<OptionValue[]>(`/options/${optionId}/values`);
   setValues(list);
  }catch(e){setError(technicalError(e))}
 }

 return <AdminShell title="Options" description="Dimensiones que generan combinaciones de Variant (Color, Talla). Para atributos descriptivos, ver Attributes.">
  {canManage&&<form className="tile" onSubmit={submit}>
   <strong>Crear Option</strong>
   <label>Código<input name="code" required/></label>
   <label>Nombre<input name="name" required/></label>
   <label>Tipo<select name="input_type" defaultValue="select"><option value="select">select</option><option value="swatch">swatch</option></select></label>
   <button>Crear Option</button>
  </form>}
  {loading?<p>Cargando…</p>:items.length===0?<p>No hay Options. Generan combinaciones de Variant (Color, Talla). Para atributos descriptivos, ver M3.2.</p>:items.map(item=>
   <div className="tile" key={item.id}>
    <div className="row">
     <span><strong>{item.name}</strong><br/>{item.code} · {item.input_type} · {item.status}</span>
     <div className="nav">
      <button className="compact" onClick={()=>toggleValues(item)}>{expanded===item.id?"Ocultar valores":"Ver valores"}</button>
      {canManage&&item.status!=="archived"&&<button className="compact" onClick={()=>archive(item)}>Archivar</button>}
     </div>
    </div>
    {expanded===item.id&&<div className="tile">
     {values.map(value=><div className="row" key={value.id}>
      <span>{value.value} ({value.code}){value.swatch_hex&&<span style={{display:"inline-block",width:12,height:12,marginLeft:6,background:value.swatch_hex,border:"1px solid #ccc"}}/>} · {value.status}</span>
      {canManageValues&&value.status!=="archived"&&<button className="compact" onClick={()=>archiveValue(item.id,value)}>Archivar</button>}
     </div>)}
     {canManageValues&&<form className="row" onSubmit={(event)=>submitValue(item.id,event)}>
      <input name="code" placeholder="código" required/>
      <input name="value" placeholder="valor" required/>
      {item.input_type==="swatch"&&<input name="swatch_hex" placeholder="#RRGGBB"/>}
      <button className="compact">Agregar valor</button>
     </form>}
    </div>}
   </div>
  )}
  {error&&<p className="error" role="alert">{error}</p>}
 </AdminShell>;
}
