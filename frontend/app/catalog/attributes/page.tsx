"use client";
import{FormEvent,useEffect,useState}from"react";
import{CatalogNav}from"@/components/CatalogNav";
import{Shell}from"@/components/Shell";
import{Attribute,AttributeDataType,AttributeOption,catalogCommand,catalogContext,catalogCreate,catalogGet,catalogPage,catalogUpdate,technicalError}from"@/lib/catalog";

const DATA_TYPES:AttributeDataType[]=["TEXT","LONG_TEXT","INTEGER","DECIMAL","BOOLEAN","DATE","DATETIME","SELECT","MULTI_SELECT"];

export default function Page(){
 const[items,setItems]=useState<Attribute[]>([]),[permissions,setPermissions]=useState<string[]>([]),[error,setError]=useState(""),[loading,setLoading]=useState(true);
 const[expanded,setExpanded]=useState<string|null>(null),[options,setOptions]=useState<AttributeOption[]>([]);
 const canManage=permissions.includes("catalog.attribute.create")||permissions.includes("catalog.attribute.update");
 const canArchive=permissions.includes("catalog.attribute.archive");
 const canManageOptions=permissions.includes("catalog.attribute_option.create");

 async function load(){
  setLoading(true);
  try{
   const[page,ctx]=await Promise.all([catalogPage<Attribute>("/attributes"),catalogContext()]);
   setItems(page.items);setPermissions(ctx.permissions);setError("");
  }catch(e){setError(technicalError(e))}finally{setLoading(false)}
 }
 useEffect(()=>{load()},[]);

 async function submit(event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  const formElement=event.currentTarget,form=new FormData(formElement);
  try{
   await catalogCreate("/attributes",{
    code:form.get("code"),
    name:form.get("name"),
    data_type:form.get("data_type"),
    unit:form.get("unit")||undefined,
    is_required:form.get("is_required")==="on",
    is_filterable:form.get("is_filterable")==="on",
    is_searchable:form.get("is_searchable")==="on",
    is_comparable:form.get("is_comparable")==="on",
   });
   formElement.reset();await load();
  }catch(e){setError(technicalError(e))}
 }

 async function archive(item:Attribute){
  try{await catalogCommand(`/attributes/${item.id}/archive`,item.version);await load()}
  catch(e){setError(technicalError(e))}
 }
 async function restore(item:Attribute){
  try{await catalogCommand(`/attributes/${item.id}/restore`,item.version);await load()}
  catch(e){setError(technicalError(e))}
 }

 async function toggleOptions(attribute:Attribute){
  if(expanded===attribute.id){setExpanded(null);return}
  try{
   const list=await catalogGet<AttributeOption[]>(`/attributes/${attribute.id}/options`);
   setOptions(list);setExpanded(attribute.id);
  }catch(e){setError(technicalError(e))}
 }

 async function submitOption(attributeId:string,event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  const formElement=event.currentTarget,form=new FormData(formElement);
  try{
   await catalogCreate(`/attributes/${attributeId}/options`,{code:form.get("code"),label:form.get("label")});
   formElement.reset();
   const list=await catalogGet<AttributeOption[]>(`/attributes/${attributeId}/options`);
   setOptions(list);
  }catch(e){setError(technicalError(e))}
 }

 async function archiveOption(attributeId:string,option:AttributeOption){
  try{
   await catalogCommand(`/attribute-options/${option.id}/archive`,option.version);
   const list=await catalogGet<AttributeOption[]>(`/attributes/${attributeId}/options`);
   setOptions(list);
  }catch(e){setError(technicalError(e))}
 }

 return <Shell title="Attributes"><CatalogNav/>
  {canManage&&<form className="tile" onSubmit={submit}>
   <strong>Crear Attribute</strong>
   <label>Código<input name="code" required/></label>
   <label>Nombre<input name="name" required/></label>
   <label>Tipo de dato<select name="data_type" defaultValue="TEXT">{DATA_TYPES.map(type=><option key={type} value={type}>{type}</option>)}</select></label>
   <label>Unidad (opcional)<input name="unit"/></label>
   <label><input type="checkbox" name="is_required"/> Obligatorio por defecto</label>
   <label><input type="checkbox" name="is_filterable"/> Filtrable</label>
   <label><input type="checkbox" name="is_searchable"/> Buscable</label>
   <label><input type="checkbox" name="is_comparable"/> Comparable</label>
   <button>Crear Attribute</button>
  </form>}
  {loading?<p>Cargando…</p>:items.length===0?<p>No hay Attributes. Describen características informativas de un producto (Potencia, Material). Para combinaciones de Variant, ver Options.</p>:items.map(item=>
   <div className="tile" key={item.id}>
    <div className="row">
     <span><strong>{item.name}</strong><br/>{item.code} · {item.data_type}{item.unit?` · ${item.unit}`:""} · {item.status}</span>
     <div className="nav">
      {(item.data_type==="SELECT"||item.data_type==="MULTI_SELECT")&&<button className="compact" onClick={()=>toggleOptions(item)}>{expanded===item.id?"Ocultar valores":"Ver valores"}</button>}
      {canArchive&&item.status!=="archived"&&<button className="compact" onClick={()=>archive(item)}>Archivar</button>}
      {canArchive&&item.status==="archived"&&<button className="compact" onClick={()=>restore(item)}>Restaurar</button>}
     </div>
    </div>
    {expanded===item.id&&<div className="tile">
     {options.map(option=><div className="row" key={option.id}>
      <span>{option.label} ({option.code}) · {option.status}</span>
      {canManageOptions&&option.status!=="archived"&&<button className="compact" onClick={()=>archiveOption(item.id,option)}>Archivar</button>}
     </div>)}
     {canManageOptions&&<form className="row" onSubmit={(event)=>submitOption(item.id,event)}>
      <input name="code" placeholder="código" required/>
      <input name="label" placeholder="etiqueta" required/>
      <button className="compact">Agregar valor</button>
     </form>}
    </div>}
   </div>
  )}
  {error&&<p className="error" role="alert">{error}</p>}
 </Shell>;
}
