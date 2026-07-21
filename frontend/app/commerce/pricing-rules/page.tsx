"use client";
import{FormEvent,useEffect,useState}from"react";
import{AdminShell}from"@/components/admin/AdminShell";
import{EmptyState}from"@/components/admin/EmptyState";
import{api}from"@/lib/api";
import{activeStore,listStores,Store}from"@/lib/platform";
import{Override,pricingCommand,pricingCreate,pricingPage,ScopeType,technicalError}from"@/lib/pricing";

type ScopeOption={id:string;name:string};

export default function Page(){
 const[items,setItems]=useState<Override[]>([]);
 const[permissions,setPermissions]=useState<string[]>([]);
 const[stores,setStores]=useState<Store[]>([]);
 const[storeId,setStoreId]=useState(activeStore()??"");
 const[channels,setChannels]=useState<ScopeOption[]>([]);
 const[markets,setMarkets]=useState<ScopeOption[]>([]);
 const[error,setError]=useState("");
 const[loading,setLoading]=useState(true);

 const canManage=permissions.includes("pricing.variant_override.manage");

 async function load(){
  setLoading(true);
  try{
   const[page,ctx,storeList]=await Promise.all([
    pricingPage<Override>("/variant-overrides"),
    api("/me/context"),
    listStores(),
   ]);
   setItems(page.items);setPermissions(ctx.permissions);setStores(storeList);setError("");
  }catch(e){setError(technicalError(e))}finally{setLoading(false)}
 }
 useEffect(()=>{load()},[]);

 useEffect(()=>{
  if(!storeId){setChannels([]);setMarkets([]);return}
  Promise.all([api(`/stores/${storeId}/channels`),api(`/stores/${storeId}/markets`)])
   .then(([channelList,marketList])=>{setChannels(channelList);setMarkets(marketList)})
   .catch(e=>setError(technicalError(e)));
 },[storeId]);

 async function submit(event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  const formElement=event.currentTarget,form=new FormData(formElement);
  const scopeType=String(form.get("scope_type"))as ScopeType;
  const scopeId=String(form.get("scope_id"));
  try{
   await pricingCreate("/variant-overrides",{
    variant_id:form.get("variant_id"),
    scope_type:scopeType,
    store_id:scopeType==="store"?scopeId:undefined,
    channel_id:scopeType==="channel"?scopeId:undefined,
    market_id:scopeType==="market"?scopeId:undefined,
    unit_amount:form.get("unit_amount"),
    compare_at_amount:form.get("compare_at_amount")||undefined,
    currency_code:form.get("currency_code"),
    priority:Number(form.get("priority")||0),
    effective_from:form.get("effective_from")||undefined,
    effective_until:form.get("effective_until")||undefined,
    reason:form.get("reason")||undefined,
   });
   formElement.reset();await load();
  }catch(e){setError(technicalError(e))}
 }

 async function archive(item:Override){
  try{await pricingCommand(`/variant-overrides/${item.id}/archive`,item.version);await load()}
  catch(e){setError(technicalError(e))}
 }

 return <AdminShell
  title="Reglas de precio"
  description="Overrides que reemplazan el precio de un Variant para un Store, Channel o Market específico, sin importar qué diga su Price List."
 >
  {canManage&&<form className="tile" onSubmit={submit}>
   <strong>Crear override</strong>
   <label>ID del Variant<input name="variant_id" placeholder="uuid del variant" required/></label>
   <label>Store<select name="store_id" value={storeId} onChange={e=>setStoreId(e.target.value)}>
    <option value="">Selecciona un store</option>
    {stores.filter(s=>s.status!=="archived").map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
   </select></label>
   <label>Tipo de scope<select name="scope_type" defaultValue="store">
    <option value="store">Store</option>
    <option value="channel">Channel</option>
    <option value="market">Market</option>
   </select></label>
   <label>Scope específico<select name="scope_id" required>
    <option value="">Selecciona…</option>
    {storeId&&<option value={storeId}>{stores.find(s=>s.id===storeId)?.name} (Store)</option>}
    {channels.map(c=><option key={c.id} value={c.id}>{c.name} (Channel)</option>)}
    {markets.map(m=><option key={m.id} value={m.id}>{m.name} (Market)</option>)}
   </select></label>
   <label>Precio<input name="unit_amount" type="number" step="0.0001" min="0" required/></label>
   <label>Precio de comparación<input name="compare_at_amount" type="number" step="0.0001" min="0"/></label>
   <label>Moneda (ISO 4217)<input name="currency_code" defaultValue="USD" maxLength={3} required/></label>
   <label>Prioridad (mayor gana)<input name="priority" type="number" defaultValue={0} min={0}/></label>
   <label>Vigente desde<input name="effective_from" type="datetime-local"/></label>
   <label>Vigente hasta<input name="effective_until" type="datetime-local"/></label>
   <label>Motivo<input name="reason" maxLength={500}/></label>
   <button>Crear override</button>
  </form>}
  {loading?<p>Cargando…</p>:items.length===0?<EmptyState title="Sin overrides todavía" description="Los overrides reemplazan cualquier Price List para un Variant en un scope puntual."/>:items.map(item=>
   <div className="row" key={item.id}>
    <span>
     <strong>{item.unit_amount} {item.currency_code}</strong> · {item.scope_type} · prioridad {item.priority} · {item.status}<br/>
     Variant {item.variant_id}{item.reason?` · ${item.reason}`:""}
    </span>
    {canManage&&item.status!=="archived"&&<button className="compact" onClick={()=>archive(item)}>Archivar</button>}
   </div>
  )}
  {error&&<p className="error" role="alert">{error}</p>}
 </AdminShell>;
}
