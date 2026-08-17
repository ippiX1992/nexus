"use client";
import{FormEvent,useEffect,useState}from"react";
import{AdminShell}from"@/components/admin/AdminShell";
import{AttributeGroup,catalogCommand,catalogContext,catalogCreate,catalogPage,technicalError}from"@/lib/catalog";
export default function Page(){
 const[items,setItems]=useState<AttributeGroup[]>([]),[permissions,setPermissions]=useState<string[]>([]),[error,setError]=useState(""),[loading,setLoading]=useState(true);
 const canManage=permissions.includes("catalog.attribute_group.create")||permissions.includes("catalog.attribute_group.update");
 const canArchive=permissions.includes("catalog.attribute_group.archive");
 async function load(){setLoading(true);try{const[page,ctx]=await Promise.all([catalogPage<AttributeGroup>("/attribute-groups"),catalogContext()]);setItems(page.items);setPermissions(ctx.permissions);setError("")}catch(e){setError(technicalError(e))}finally{setLoading(false)}}
 useEffect(()=>{load()},[]);
 async function submit(event:FormEvent<HTMLFormElement>){event.preventDefault();const formElement=event.currentTarget,form=new FormData(formElement);try{await catalogCreate("/attribute-groups",{code:form.get("code"),name:form.get("name")});formElement.reset();await load()}catch(e){setError(technicalError(e))}}
 async function archive(item:AttributeGroup){try{await catalogCommand(`/attribute-groups/${item.id}/archive`,item.version);await load()}catch(e){setError(technicalError(e))}}
 async function restore(item:AttributeGroup){try{await catalogCommand(`/attribute-groups/${item.id}/restore`,item.version);await load()}catch(e){setError(technicalError(e))}}
 return <AdminShell title="Grupos de atributos" description="Agrupan especificaciones relacionadas (Dimensiones, Eléctrico, Garantía).">
  {canManage&&<form className="tile" onSubmit={submit}>
   <strong>Crear Attribute Group</strong>
   <label>Código<input name="code" required/></label>
   <label>Nombre<input name="name" required/></label>
   <button>Crear Attribute Group</button>
  </form>}
  {loading?<p>Cargando…</p>:items.length===0?<p>No hay Attribute Groups. Agrupan especificaciones (Dimensiones, Eléctrico, Garantía).</p>:items.map(item=>
   <div className="row" key={item.id}>
    <span><strong>{item.name}</strong><br/>{item.code} · {item.status}</span>
    <div className="nav">
     {canArchive&&item.status!=="archived"&&<button className="compact" onClick={()=>archive(item)}>Archivar</button>}
     {canArchive&&item.status==="archived"&&<button className="compact" onClick={()=>restore(item)}>Restaurar</button>}
    </div>
   </div>
  )}
  {error&&<p className="error" role="alert">{error}</p>}
 </AdminShell>;
}
