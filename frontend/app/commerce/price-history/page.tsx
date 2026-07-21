"use client";
import{FormEvent,useEffect,useState}from"react";
import{AdminShell}from"@/components/admin/AdminShell";
import{EmptyState}from"@/components/admin/EmptyState";
import{PriceHistoryEntry,pricingPage,technicalError}from"@/lib/pricing";

export default function Page(){
 const[items,setItems]=useState<PriceHistoryEntry[]>([]);
 const[variantId,setVariantId]=useState("");
 const[error,setError]=useState("");
 const[loading,setLoading]=useState(true);

 async function load(filterVariantId?:string){
  setLoading(true);
  try{
   const query=filterVariantId?`?variant_id=${filterVariantId}`:"";
   const page=await pricingPage<PriceHistoryEntry>(`/price-history${query}`);
   setItems(page.items);setError("");
  }catch(e){setError(technicalError(e))}finally{setLoading(false)}
 }
 useEffect(()=>{load()},[]);

 function submit(event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  load(variantId||undefined);
 }

 return <AdminShell title="Historial de precios" description="Cada cambio de precio base, comparación, MSRP o costo queda registrado aquí, con el valor anterior y el nuevo.">
  <form className="row" onSubmit={submit}>
   <input placeholder="Filtrar por ID de Variant" value={variantId} onChange={e=>setVariantId(e.target.value)}/>
   <button className="compact">Filtrar</button>
  </form>
  {loading?<p>Cargando…</p>:items.length===0?<EmptyState title="Sin historial todavía" description="Los cambios de precio aparecerán aquí en cuanto se edite una Price List Entry o un override."/>:items.map(item=>
   <div className="row" key={item.id}>
    <span>
     <strong>{item.field_name}</strong>: {item.previous_amount??"—"} → {item.new_amount??"—"} {item.currency_code}<br/>
     {item.entity_type} · Variant {item.variant_id} · {new Date(item.changed_at).toLocaleString()}{item.reason?` · ${item.reason}`:""}
    </span>
   </div>
  )}
  {error&&<p className="error" role="alert">{error}</p>}
 </AdminShell>;
}
