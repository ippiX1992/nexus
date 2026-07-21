"use client";
import{FormEvent,useEffect,useState}from"react";
import Link from"next/link";
import{AdminShell}from"@/components/admin/AdminShell";
import{PriceList,pricingCommand,pricingCreate,pricingPage,technicalError}from"@/lib/pricing";
import{api}from"@/lib/api";

export default function Page(){
 const[items,setItems]=useState<PriceList[]>([]),[permissions,setPermissions]=useState<string[]>([]),[error,setError]=useState(""),[loading,setLoading]=useState(true);
 const canManage=permissions.includes("pricing.price_list.create");
 const canArchive=permissions.includes("pricing.price_list.archive");
 async function load(){
  setLoading(true);
  try{
   const[page,ctx]=await Promise.all([pricingPage<PriceList>("/price-lists"),api("/me/context")]);
   setItems(page.items);setPermissions(ctx.permissions);setError("");
  }catch(e){setError(technicalError(e))}finally{setLoading(false)}
 }
 useEffect(()=>{load()},[]);

 async function submit(event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  const formElement=event.currentTarget,form=new FormData(formElement);
  try{
   await pricingCreate("/price-lists",{
    code:form.get("code"),
    name:form.get("name"),
    currency_code:form.get("currency_code"),
    is_default:form.get("is_default")==="on",
   });
   formElement.reset();await load();
  }catch(e){setError(technicalError(e))}
 }

 async function archive(item:PriceList){
  try{await pricingCommand(`/price-lists/${item.id}/archive`,item.version);await load()}
  catch(e){setError(technicalError(e))}
 }

 return <AdminShell title="Price Lists" description="Listas de precios por moneda. Se asignan a Store, Channel o Market con prioridad y vigencia.">
  {canManage&&<form className="tile" onSubmit={submit}>
   <strong>Crear Price List</strong>
   <label>Código<input name="code" required/></label>
   <label>Nombre<input name="name" required/></label>
   <label>Moneda (ISO 4217)<input name="currency_code" defaultValue="USD" maxLength={3} required/></label>
   <label><input type="checkbox" name="is_default"/> Lista por defecto del tenant</label>
   <button>Crear Price List</button>
  </form>}
  {loading?<p>Cargando…</p>:items.length===0?<p>No hay Price Lists todavía.</p>:items.map(item=>
   <div className="row" key={item.id}>
    <span>
     <Link href={`/commerce/price-lists/${item.id}`}><strong>{item.name}</strong></Link>
     {item.is_default&&" · por defecto"}
     <br/>{item.code} · {item.currency_code} · {item.status} · v{item.version}
    </span>
    <div className="nav">
     <Link className="button compact" href={`/commerce/price-lists/${item.id}`}>Ver precios</Link>
     {canArchive&&item.status!=="archived"&&<button className="compact" onClick={()=>archive(item)}>Archivar</button>}
    </div>
   </div>
  )}
  {error&&<p className="error" role="alert">{error}</p>}
 </AdminShell>;
}
