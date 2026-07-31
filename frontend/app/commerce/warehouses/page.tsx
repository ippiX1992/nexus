"use client";
import{FormEvent,useEffect,useState}from"react";
import Link from"next/link";
import{AdminShell}from"@/components/admin/AdminShell";
import{EmptyState}from"@/components/admin/EmptyState";
import{Warehouse,inventoryCommand,inventoryCreate,inventoryPage,technicalError}from"@/lib/inventory";
import{api}from"@/lib/api";

export default function Page(){
 const[items,setItems]=useState<Warehouse[]>([]),[permissions,setPermissions]=useState<string[]>([]),[error,setError]=useState(""),[loading,setLoading]=useState(true);
 const canManage=permissions.includes("inventory.warehouse.create");
 const canArchive=permissions.includes("inventory.warehouse.archive");
 async function load(){
  setLoading(true);
  try{
   const[page,ctx]=await Promise.all([inventoryPage<Warehouse>("/warehouses"),api("/me/context")]);
   setItems(page.items);setPermissions(ctx.permissions);setError("");
  }catch(e){setError(technicalError(e))}finally{setLoading(false)}
 }
 useEffect(()=>{load()},[]);

 async function submit(event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  const formElement=event.currentTarget,form=new FormData(formElement);
  try{
   await inventoryCreate("/warehouses",{code:form.get("code"),name:form.get("name"),country_code:form.get("country_code")||null});
   formElement.reset();await load();
  }catch(e){setError(technicalError(e))}
 }
 async function archive(item:Warehouse){
  try{await inventoryCommand(`/warehouses/${item.id}/archive`,item.version);await load()}
  catch(e){setError(technicalError(e))}
 }

 return <AdminShell title="Warehouses" description="Centros físicos o lógicos que guardan stock. Cada uno agrupa Locations y se asigna a Store/Channel/Market para asignación (allocation).">
  {canManage&&<form className="tile" onSubmit={submit}>
   <strong>Crear Warehouse</strong>
   <label>Código<input name="code" required/></label>
   <label>Nombre<input name="name" required/></label>
   <label>País (ISO, opcional)<input name="country_code" maxLength={2}/></label>
   <button>Crear Warehouse</button>
  </form>}
  {loading?<p>Cargando…</p>:items.length===0?<EmptyState title="Sin Warehouses todavía" description="Crea el primero para empezar a registrar stock."/>:items.map(item=>
   <div className="row" key={item.id}>
    <span>
     <Link href={`/commerce/warehouses/${item.id}`}><strong>{item.name}</strong></Link>
     <br/>{item.code}{item.country_code?` · ${item.country_code}`:""} · {item.status} · v{item.version}
    </span>
    <div className="nav">
     <Link className="button compact" href={`/commerce/warehouses/${item.id}`}>Locations &amp; scopes</Link>
     {canArchive&&item.status!=="archived"&&<button className="compact" onClick={()=>archive(item)}>Archivar</button>}
    </div>
   </div>
  )}
  {error&&<p className="error" role="alert">{error}</p>}
 </AdminShell>;
}
