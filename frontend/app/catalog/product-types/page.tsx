"use client";
import{FormEvent,useEffect,useState}from"react";
import{AdminShell}from"@/components/admin/AdminShell";
import{Attribute,catalogCommand,catalogContext,catalogCreate,catalogGet,catalogPage,catalogUpdate,ProductType,ProductTypeAttribute,technicalError}from"@/lib/catalog";

export default function Page(){
 const[items,setItems]=useState<ProductType[]>([]),[permissions,setPermissions]=useState<string[]>([]),[error,setError]=useState(""),[loading,setLoading]=useState(true);
 const[attributes,setAttributes]=useState<Attribute[]>([]),[expanded,setExpanded]=useState<string|null>(null),[assigned,setAssigned]=useState<ProductTypeAttribute[]>([]);
 const canManage=permissions.includes("catalog.product_type.manage");
 const canManageAttributes=permissions.includes("catalog.product_type_attribute.manage");

 async function load(){
  setLoading(true);
  try{
   const[page,ctx,attributePage]=await Promise.all([catalogPage<ProductType>("/product-types"),catalogContext(),catalogPage<Attribute>("/attributes")]);
   setItems(page.items);setPermissions(ctx.permissions);setAttributes(attributePage.items.filter(item=>item.status!=="archived"));setError("");
  }catch(e){setError(technicalError(e))}finally{setLoading(false)}
 }
 useEffect(()=>{load()},[]);

 async function submit(event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  const formElement=event.currentTarget,form=new FormData(formElement);
  try{
   await catalogCreate("/product-types",{code:form.get("code"),name:form.get("name"),description:form.get("description")||null});
   formElement.reset();await load();
  }catch(e){setError(technicalError(e))}
 }

 async function archive(item:ProductType){try{await catalogCommand(`/product-types/${item.id}/archive`,item.version);await load()}catch(e){setError(technicalError(e))}}

 async function toggleAttributes(item:ProductType){
  if(expanded===item.id){setExpanded(null);return}
  try{
   const list=await catalogGet<ProductTypeAttribute[]>(`/product-types/${item.id}/attributes`);
   setAssigned(list);setExpanded(item.id);
  }catch(e){setError(technicalError(e))}
 }

 async function addAttribute(item:ProductType,attributeId:string){
  if(!attributeId)return;
  const attribute=attributes.find(a=>a.id===attributeId);
  const next=assigned.map(a=>({attribute_id:a.attribute_id,group_id:a.group_id,position:a.position,required:a.required}));
  next.push({attribute_id:attributeId,group_id:undefined,position:next.length,required:attribute?.is_required??false});
  try{
   await catalogUpdate(`/product-types/${item.id}/attributes`,{attributes:next},item.version,"PUT");
   await load();
   const list=await catalogGet<ProductTypeAttribute[]>(`/product-types/${item.id}/attributes`);
   setAssigned(list);
  }catch(e){setError(technicalError(e))}
 }

 async function removeAttribute(item:ProductType,attributeId:string){
  const next=assigned.filter(a=>a.attribute_id!==attributeId).map(a=>({attribute_id:a.attribute_id,group_id:a.group_id,position:a.position,required:a.required}));
  try{
   await catalogUpdate(`/product-types/${item.id}/attributes`,{attributes:next},item.version,"PUT");
   await load();
   const list=await catalogGet<ProductTypeAttribute[]>(`/product-types/${item.id}/attributes`);
   setAssigned(list);
  }catch(e){setError(technicalError(e))}
 }

 async function toggleRequired(item:ProductType,attributeId:string,required:boolean){
  const next=assigned.map(a=>({attribute_id:a.attribute_id,group_id:a.group_id,position:a.position,required:a.attribute_id===attributeId?required:a.required}));
  try{
   await catalogUpdate(`/product-types/${item.id}/attributes`,{attributes:next},item.version,"PUT");
   await load();
   const list=await catalogGet<ProductTypeAttribute[]>(`/product-types/${item.id}/attributes`);
   setAssigned(list);
  }catch(e){setError(technicalError(e))}
 }

 return <AdminShell title="Tipos de producto" description="Define qué Attributes aplican a cada tipo de producto.">
  {canManage&&<form className="tile" onSubmit={submit}>
   <strong>Crear Product Type</strong>
   <label>Código<input name="code" required/></label>
   <label>Nombre<input name="name" required/></label>
   <label>Descripción<input name="description"/></label>
   <button>Crear Product Type</button>
  </form>}
  {loading?<p>Cargando…</p>:items.length===0?<p>No hay Product Types.</p>:items.map(item=>
   <div className="tile" key={item.id}>
    <div className="row">
     <span><strong>{item.name}</strong><br/>{item.code} · {item.status} · v{item.version}</span>
     <div className="nav">
      <button className="compact" onClick={()=>toggleAttributes(item)}>{expanded===item.id?"Ocultar Attributes":"Ver Attributes"}</button>
      {canManage&&item.status!=="archived"&&<button className="compact" onClick={()=>archive(item)}>Archivar</button>}
     </div>
    </div>
    {expanded===item.id&&<div className="tile">
     {assigned.length===0?<p>Sin Attributes asignados.</p>:assigned.map(entry=>
      <div className="row" key={entry.attribute_id}>
       <span>{attributes.find(a=>a.id===entry.attribute_id)?.name??entry.attribute_id}{entry.required?" · obligatorio":""}</span>
       {canManageAttributes&&<div className="nav">
        <label><input type="checkbox" checked={entry.required} onChange={event=>toggleRequired(item,entry.attribute_id,event.target.checked)}/> Obligatorio</label>
        <button className="compact" onClick={()=>removeAttribute(item,entry.attribute_id)}>Quitar</button>
       </div>}
      </div>
     )}
     {canManageAttributes&&<label>Agregar Attribute<select aria-label="Agregar Attribute" defaultValue="" onChange={event=>{addAttribute(item,event.target.value);event.target.value=""}}>
      <option value="">Selecciona</option>
      {attributes.filter(a=>!assigned.some(entry=>entry.attribute_id===a.id)).map(a=><option key={a.id} value={a.id}>{a.name}</option>)}
     </select></label>}
    </div>}
   </div>
  )}
  {error&&<p className="error" role="alert">{error}</p>}
 </AdminShell>;
}
