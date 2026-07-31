"use client";
import{FormEvent,useEffect,useState}from"react";
import{AdminShell}from"@/components/admin/AdminShell";
import{EmptyState}from"@/components/admin/EmptyState";
import{api}from"@/lib/api";
import{
 LedgerEntry,
 Location,
 StockLevel,
 Warehouse,
 inventoryAction,
 inventoryPage,
 technicalError,
}from"@/lib/inventory";

export default function Page(){
 const[warehouses,setWarehouses]=useState<Warehouse[]>([]);
 const[locations,setLocations]=useState<Location[]>([]);
 const[levels,setLevels]=useState<StockLevel[]>([]);
 const[ledger,setLedger]=useState<LedgerEntry[]>([]);
 const[permissions,setPermissions]=useState<string[]>([]);
 const[variantFilter,setVariantFilter]=useState("");
 const[error,setError]=useState("");
 const[loading,setLoading]=useState(true);

 const canAdjust=permissions.includes("inventory.stock.adjust");
 const canRecount=permissions.includes("inventory.stock.recount");

 async function load(variantId?:string){
  setLoading(true);
  try{
   const query=variantId?`?variant_id=${variantId}`:"";
   const[levelPage,ledgerPage,warehousePage,locationPage,ctx]=await Promise.all([
    inventoryPage<StockLevel>(`/stock${query}`),
    inventoryPage<LedgerEntry>(`/ledger${query}`),
    inventoryPage<Warehouse>("/warehouses"),
    inventoryPage<Location>("/locations"),
    api("/me/context"),
   ]);
   setLevels(levelPage.items);setLedger(ledgerPage.items);setWarehouses(warehousePage.items);
   setLocations(locationPage.items);setPermissions(ctx.permissions);setError("");
  }catch(e){setError(technicalError(e))}finally{setLoading(false)}
 }
 useEffect(()=>{load()},[]);

 const locationName=(id:string)=>locations.find(l=>l.id===id)?.name??id;

 async function submitMovement(event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  const formElement=event.currentTarget,form=new FormData(formElement);
  const kind=String(form.get("kind"));
  const locationId=String(form.get("location_id"));
  const variantId=String(form.get("variant_id"));
  const amount=Number(form.get("amount"));
  const reason=form.get("reason")||undefined;
  try{
   if(kind==="receive")await inventoryAction(`/locations/${locationId}/variants/${variantId}/receive`,{quantity:amount,reason});
   else if(kind==="adjust")await inventoryAction(`/locations/${locationId}/variants/${variantId}/adjust`,{delta:amount,reason});
   else await inventoryAction(`/locations/${locationId}/variants/${variantId}/recount`,{counted:amount,reason});
   formElement.reset();await load(variantFilter||undefined);
  }catch(e){setError(technicalError(e))}
 }

 function filter(event:FormEvent<HTMLFormElement>){event.preventDefault();load(variantFilter||undefined)}

 return <AdminShell title="Inventario" description="Stock por Variant y Location: disponible = on_hand − reservado. Recepciones, ajustes y recuentos quedan en el ledger inmutable.">
  {(canAdjust||canRecount)&&<form className="tile" onSubmit={submitMovement}>
   <strong>Movimiento de stock</strong>
   <label>Tipo<select name="kind" defaultValue="receive">
    <option value="receive">Recepción (+)</option>
    <option value="adjust">Ajuste (±)</option>
    <option value="recount">Recuento (=)</option>
   </select></label>
   <label>Location<select name="location_id" required>
    <option value="">Selecciona…</option>
    {locations.filter(l=>l.status!=="archived").map(l=>{
     const wh=warehouses.find(w=>w.id===l.warehouse_id);
     return <option key={l.id} value={l.id}>{wh?`${wh.code} / `:""}{l.name}</option>;
    })}
   </select></label>
   <label>ID del Variant<input name="variant_id" placeholder="uuid del variant" required/></label>
   <label>Cantidad<input name="amount" type="number" required/></label>
   <label>Motivo<input name="reason" maxLength={500}/></label>
   <button>Aplicar movimiento</button>
  </form>}

  <form className="row" onSubmit={filter}>
   <input placeholder="Filtrar por ID de Variant" value={variantFilter} onChange={e=>setVariantFilter(e.target.value)}/>
   <button className="compact">Filtrar</button>
  </form>

  <h2>Niveles de stock</h2>
  {loading?<p>Cargando…</p>:levels.length===0?<EmptyState title="Sin stock todavía" description="Registra una recepción para crear el primer nivel de stock."/>:levels.map(level=>
   <div className="row" key={level.id}>
    <span>
     <strong>{locationName(level.location_id)}</strong><br/>
     Variant {level.variant_id}<br/>
     on_hand {level.on_hand} · reservado {level.reserved} · disponible {level.available} · incoming {level.incoming}
    </span>
   </div>
  )}

  <h2>Ledger</h2>
  {ledger.length===0?<EmptyState title="Sin movimientos" description="Cada recepción, ajuste, recuento, transferencia o reserva aparecerá aquí."/>:ledger.map(entry=>
   <div className="row" key={entry.id}>
    <span>
     <strong>{entry.entry_type}</strong> · {entry.quantity_delta>=0?`+${entry.quantity_delta}`:entry.quantity_delta} → {entry.on_hand_after}<br/>
     {locationName(entry.location_id)} · {new Date(entry.created_at).toLocaleString()}{entry.reason?` · ${entry.reason}`:""}
    </span>
   </div>
  )}
  {error&&<p className="error" role="alert">{error}</p>}
 </AdminShell>;
}
