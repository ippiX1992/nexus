"use client";
import{FormEvent,useEffect,useState}from"react";
import{useParams}from"next/navigation";
import{AdminShell}from"@/components/admin/AdminShell";
import{EmptyState}from"@/components/admin/EmptyState";
import{api}from"@/lib/api";
import{activeStore,listStores,Store}from"@/lib/platform";
import{
 FulfillmentScope,
 Location,
 ScopeType,
 Warehouse,
 inventoryCommand,
 inventoryCreate,
 inventoryGet,
 inventoryPage,
 technicalError,
}from"@/lib/inventory";

type ScopeOption={id:string;name:string};

export default function Page(){
 const params=useParams();
 const warehouseId=String(params.id);
 const[warehouse,setWarehouse]=useState<Warehouse|null>(null);
 const[locations,setLocations]=useState<Location[]>([]);
 const[scopes,setScopes]=useState<FulfillmentScope[]>([]);
 const[permissions,setPermissions]=useState<string[]>([]);
 const[stores,setStores]=useState<Store[]>([]);
 const[storeId,setStoreId]=useState(activeStore()??"");
 const[channels,setChannels]=useState<ScopeOption[]>([]);
 const[markets,setMarkets]=useState<ScopeOption[]>([]);
 const[error,setError]=useState("");
 const[loading,setLoading]=useState(true);

 const canManageLocations=permissions.includes("inventory.location.create");
 const canManageScopes=permissions.includes("inventory.fulfillment_scope.manage");

 async function load(){
  setLoading(true);
  try{
   const[wh,locationPage,scopePage,ctx,storeList]=await Promise.all([
    inventoryGet<Warehouse>(`/warehouses/${warehouseId}`),
    inventoryPage<Location>(`/locations?warehouse_id=${warehouseId}`),
    inventoryPage<FulfillmentScope>(`/fulfillment-scopes?warehouse_id=${warehouseId}`),
    api("/me/context"),
    listStores(),
   ]);
   setWarehouse(wh);setLocations(locationPage.items);setScopes(scopePage.items);
   setPermissions(ctx.permissions);setStores(storeList);setError("");
  }catch(e){setError(technicalError(e))}finally{setLoading(false)}
 }
 useEffect(()=>{load()},[warehouseId]);

 useEffect(()=>{
  if(!storeId){setChannels([]);setMarkets([]);return}
  Promise.all([api(`/stores/${storeId}/channels`),api(`/stores/${storeId}/markets`)])
   .then(([c,m])=>{setChannels(c);setMarkets(m)})
   .catch(e=>setError(technicalError(e)));
 },[storeId]);

 async function submitLocation(event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  const formElement=event.currentTarget,form=new FormData(formElement);
  try{
   await inventoryCreate(`/warehouses/${warehouseId}/locations`,{code:form.get("code"),name:form.get("name"),location_type:form.get("location_type")});
   formElement.reset();await load();
  }catch(e){setError(technicalError(e))}
 }
 async function submitScope(event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  const formElement=event.currentTarget,form=new FormData(formElement);
  const scopeType=String(form.get("scope_type"))as ScopeType;
  const scopeId=String(form.get("scope_id"));
  try{
   await inventoryCreate("/fulfillment-scopes",{
    warehouse_id:warehouseId,
    scope_type:scopeType,
    store_id:scopeType==="store"?scopeId:undefined,
    channel_id:scopeType==="channel"?scopeId:undefined,
    market_id:scopeType==="market"?scopeId:undefined,
    priority:Number(form.get("priority")||0),
   });
   formElement.reset();await load();
  }catch(e){setError(technicalError(e))}
 }
 async function archiveScope(item:FulfillmentScope){
  try{await inventoryCommand(`/fulfillment-scopes/${item.id}/archive`,item.version);await load()}
  catch(e){setError(technicalError(e))}
 }

 if(loading&&!warehouse)return <AdminShell title="Warehouse">Cargando…</AdminShell>;
 if(!warehouse)return <AdminShell title="Warehouse"><p className="error" role="alert">{error||"No encontrado"}</p></AdminShell>;

 return <AdminShell title={warehouse.name} description={`${warehouse.code} · ${warehouse.status}`}>
  <h2>Locations</h2>
  {canManageLocations&&<form className="tile" onSubmit={submitLocation}>
   <strong>Crear Location</strong>
   <label>Código<input name="code" required/></label>
   <label>Nombre<input name="name" required/></label>
   <label>Tipo<select name="location_type" defaultValue="storage">
    {["storage","picking","staging","returns","quarantine"].map(t=><option key={t} value={t}>{t}</option>)}
   </select></label>
   <button>Crear Location</button>
  </form>}
  {locations.length===0?<EmptyState title="Sin Locations" description="Agrega una Location para poder registrar stock en este warehouse."/>:locations.map(loc=>
   <div className="row" key={loc.id}><span><strong>{loc.name}</strong><br/>{loc.code} · {loc.location_type} · {loc.status}</span></div>
  )}

  <h2>Fulfillment scopes (asignación a Store / Channel / Market)</h2>
  {canManageScopes&&<form className="tile" onSubmit={submitScope}>
   <strong>Asignar este warehouse a un scope</strong>
   <label>Store<select name="store_id" value={storeId} onChange={e=>setStoreId(e.target.value)}>
    <option value="">Selecciona un store</option>
    {stores.filter(s=>s.status!=="archived").map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
   </select></label>
   <label>Tipo de scope<select name="scope_type" defaultValue="channel">
    <option value="store">Store</option><option value="channel">Channel</option><option value="market">Market</option>
   </select></label>
   <label>Scope específico<select name="scope_id" required>
    <option value="">Selecciona…</option>
    {storeId&&<option value={storeId}>{stores.find(s=>s.id===storeId)?.name} (Store)</option>}
    {channels.map(c=><option key={c.id} value={c.id}>{c.name} (Channel)</option>)}
    {markets.map(m=><option key={m.id} value={m.id}>{m.name} (Market)</option>)}
   </select></label>
   <label>Prioridad (mayor asigna primero)<input name="priority" type="number" defaultValue={0} min={0}/></label>
   <button>Crear scope</button>
  </form>}
  {scopes.length===0?<EmptyState title="Sin scopes" description="Este warehouse no sirve todavía a ningún Store, Channel o Market."/>:scopes.map(scope=>
   <div className="row" key={scope.id}>
    <span><strong>{scope.scope_type}</strong> · prioridad {scope.priority} · {scope.status}</span>
    {canManageScopes&&scope.status!=="archived"&&<button className="compact" onClick={()=>archiveScope(scope)}>Archivar</button>}
   </div>
  )}
  {error&&<p className="error" role="alert">{error}</p>}
 </AdminShell>;
}
