"use client";
import{FormEvent,useEffect,useState}from"react";
import{useParams}from"next/navigation";
import{AdminShell}from"@/components/admin/AdminShell";
import{EmptyState}from"@/components/admin/EmptyState";
import{api}from"@/lib/api";
import{variantLabels}from"@/lib/catalog";
import{activeStore,listStores,Store}from"@/lib/platform";
import{
 Assignment,
 PriceList,
 PriceListEntry,
 pricingCommand,
 pricingCreate,
 pricingGet,
 pricingPage,
 pricingPut,
 ScopeType,
 technicalError,
}from"@/lib/pricing";

type ScopeOption={id:string;name:string};

export default function Page(){
 const params=useParams();
 const priceListId=String(params.id);
 const[priceList,setPriceList]=useState<PriceList|null>(null);
 const[entries,setEntries]=useState<PriceListEntry[]>([]);
 const[assignments,setAssignments]=useState<Assignment[]>([]);
 const[permissions,setPermissions]=useState<string[]>([]);
 const[stores,setStores]=useState<Store[]>([]);
 const[storeId,setStoreId]=useState(activeStore()??"");
 const[channels,setChannels]=useState<ScopeOption[]>([]);
 const[markets,setMarkets]=useState<ScopeOption[]>([]);
 const[names,setNames]=useState<Map<string,string>>(new Map());
 const[error,setError]=useState("");
 const[loading,setLoading]=useState(true);

 const canManageEntries=permissions.includes("pricing.price_list_entry.manage");
 const canManageAssignments=permissions.includes("pricing.assignment.manage");

 async function load(){
  setLoading(true);
  try{
   const[list,entryPage,assignmentPage,ctx,storeList,labels]=await Promise.all([
    pricingGet<PriceList>(`/price-lists/${priceListId}`),
    pricingPage<PriceListEntry>(`/price-lists/${priceListId}/entries`),
    pricingPage<Assignment>(`/assignments?price_list_id=${priceListId}`),
    api("/me/context"),
    listStores(),
    variantLabels().catch(()=>new Map<string,string>()),
   ]);
   setPriceList(list);setEntries(entryPage.items);setAssignments(assignmentPage.items);
   setPermissions(ctx.permissions);setStores(storeList);setNames(labels);setError("");
  }catch(e){setError(technicalError(e))}finally{setLoading(false)}
 }
 useEffect(()=>{load()},[priceListId]);

 const variantName=(id:string)=>names.get(id)??id;

 useEffect(()=>{
  if(!storeId){setChannels([]);setMarkets([]);return}
  Promise.all([api(`/stores/${storeId}/channels`),api(`/stores/${storeId}/markets`)])
   .then(([channelList,marketList])=>{setChannels(channelList);setMarkets(marketList)})
   .catch(e=>setError(technicalError(e)));
 },[storeId]);

 async function submitEntry(event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  const formElement=event.currentTarget,form=new FormData(formElement);
  const variantId=String(form.get("variant_id"));
  try{
   await pricingPut(`/price-lists/${priceListId}/entries/${variantId}`,{
    unit_amount:form.get("unit_amount"),
    compare_at_amount:form.get("compare_at_amount")||null,
    msrp_amount:form.get("msrp_amount")||null,
    cost_amount:form.get("cost_amount")||null,
   });
   formElement.reset();await load();
  }catch(e){setError(technicalError(e))}
 }

 async function submitAssignment(event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  const formElement=event.currentTarget,form=new FormData(formElement);
  const scopeType=String(form.get("scope_type"))as ScopeType;
  const scopeId=String(form.get("scope_id"));
  try{
   await pricingCreate("/assignments",{
    price_list_id:priceListId,
    scope_type:scopeType,
    store_id:scopeType==="store"?scopeId:undefined,
    channel_id:scopeType==="channel"?scopeId:undefined,
    market_id:scopeType==="market"?scopeId:undefined,
    priority:Number(form.get("priority")||0),
    effective_from:form.get("effective_from")||undefined,
    effective_until:form.get("effective_until")||undefined,
   });
   formElement.reset();await load();
  }catch(e){setError(technicalError(e))}
 }

 async function archiveAssignment(item:Assignment){
  try{await pricingCommand(`/assignments/${item.id}/archive`,item.version);await load()}
  catch(e){setError(technicalError(e))}
 }

 if(loading&&!priceList)return <AdminShell title="Price List">Cargando…</AdminShell>;
 if(!priceList)return <AdminShell title="Price List"><p className="error" role="alert">{error||"No encontrado"}</p></AdminShell>;

 return <AdminShell
  title={priceList.name}
  description={`${priceList.code} · ${priceList.currency_code} · ${priceList.status}${priceList.is_default?" · lista por defecto":""}`}
 >
  <h2>Precios por Variant</h2>
  {canManageEntries&&<form className="tile" onSubmit={submitEntry}>
   <strong>Definir precio de un Variant</strong>
   <label>ID del Variant<input name="variant_id" placeholder="uuid del variant" required/></label>
   <label>Precio base<input name="unit_amount" type="number" step="0.0001" min="0" required/></label>
   <label>Precio de comparación<input name="compare_at_amount" type="number" step="0.0001" min="0"/></label>
   <label>MSRP<input name="msrp_amount" type="number" step="0.0001" min="0"/></label>
   <label>Costo<input name="cost_amount" type="number" step="0.0001" min="0"/></label>
   <button>Guardar precio</button>
  </form>}
  {entries.length===0?<EmptyState title="Sin precios todavía" description="Agrega el primer Variant para empezar esta Price List."/>:entries.map(entry=>
   <div className="row" key={entry.id}>
    <span>
     <strong>{variantName(entry.variant_id)}</strong><br/>
     Base {entry.unit_amount}{entry.compare_at_amount?` · Comparación ${entry.compare_at_amount}`:""}{entry.msrp_amount?` · MSRP ${entry.msrp_amount}`:""}{entry.cost_amount?` · Costo ${entry.cost_amount}`:""} · v{entry.version}
    </span>
   </div>
  )}

  <h2>Asignaciones (Store / Channel / Market)</h2>
  {canManageAssignments&&<form className="tile" onSubmit={submitAssignment}>
   <strong>Asignar esta Price List a un scope</strong>
   <label>Store<select name="store_id" value={storeId} onChange={e=>setStoreId(e.target.value)}>
    <option value="">Selecciona un store</option>
    {stores.filter(s=>s.status!=="archived").map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
   </select></label>
   <label>Tipo de scope<select name="scope_type" defaultValue="channel">
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
   <label>Prioridad (mayor gana)<input name="priority" type="number" defaultValue={0} min={0}/></label>
   <label>Vigente desde<input name="effective_from" type="datetime-local"/></label>
   <label>Vigente hasta<input name="effective_until" type="datetime-local"/></label>
   <button>Crear asignación</button>
  </form>}
  {assignments.length===0?<EmptyState title="Sin asignaciones" description="Esta Price List no se aplica a ningún Store, Channel o Market todavía."/>:assignments.map(item=>
   <div className="row" key={item.id}>
    <span>
     <strong>{item.scope_type}</strong> · prioridad {item.priority} · {item.status}<br/>
     {item.effective_from?`desde ${item.effective_from}`:"sin inicio"} · {item.effective_until?`hasta ${item.effective_until}`:"sin fin"}
    </span>
    {canManageAssignments&&item.status!=="archived"&&<button className="compact" onClick={()=>archiveAssignment(item)}>Archivar</button>}
   </div>
  )}

  {error&&<p className="error" role="alert">{error}</p>}
 </AdminShell>;
}
