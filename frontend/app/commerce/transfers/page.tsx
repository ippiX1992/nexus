"use client";
import{FormEvent,useEffect,useState}from"react";
import{AdminShell}from"@/components/admin/AdminShell";
import{EmptyState}from"@/components/admin/EmptyState";
import{api}from"@/lib/api";
import{Location,Transfer,Warehouse,inventoryCommand,inventoryCreate,inventoryPage,technicalError}from"@/lib/inventory";

export default function Page(){
 const[items,setItems]=useState<Transfer[]>([]);
 const[locations,setLocations]=useState<Location[]>([]);
 const[warehouses,setWarehouses]=useState<Warehouse[]>([]);
 const[permissions,setPermissions]=useState<string[]>([]);
 const[error,setError]=useState("");
 const[loading,setLoading]=useState(true);

 const canManage=permissions.includes("inventory.transfer.manage");

 async function load(){
  setLoading(true);
  try{
   const[transferPage,locationPage,warehousePage,ctx]=await Promise.all([
    inventoryPage<Transfer>("/transfers"),
    inventoryPage<Location>("/locations"),
    inventoryPage<Warehouse>("/warehouses"),
    api("/me/context"),
   ]);
   setItems(transferPage.items);setLocations(locationPage.items);setWarehouses(warehousePage.items);
   setPermissions(ctx.permissions);setError("");
  }catch(e){setError(technicalError(e))}finally{setLoading(false)}
 }
 useEffect(()=>{load()},[]);

 const locationLabel=(id:string)=>{
  const loc=locations.find(l=>l.id===id);
  const wh=loc&&warehouses.find(w=>w.id===loc.warehouse_id);
  return loc?`${wh?`${wh.code} / `:""}${loc.name}`:id;
 };

 async function submit(event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  const formElement=event.currentTarget,form=new FormData(formElement);
  try{
   await inventoryCreate("/transfers",{
    from_location_id:form.get("from_location_id"),
    to_location_id:form.get("to_location_id"),
    variant_id:form.get("variant_id"),
    quantity:Number(form.get("quantity")),
    reason:form.get("reason")||undefined,
   });
   formElement.reset();await load();
  }catch(e){setError(technicalError(e))}
 }
 async function complete(item:Transfer){try{await inventoryCommand(`/transfers/${item.id}/complete`,item.version);await load()}catch(e){setError(technicalError(e))}}
 async function cancel(item:Transfer){try{await inventoryCommand(`/transfers/${item.id}/cancel`,item.version);await load()}catch(e){setError(technicalError(e))}}

 const activeLocations=locations.filter(l=>l.status!=="archived");

 return <AdminShell title="Transferencias" description="Mueve stock entre Locations. Mientras está in_transit, sale del origen y cuenta como incoming en el destino; al completarse aterriza en on_hand.">
  {canManage&&<form className="tile" onSubmit={submit}>
   <strong>Crear transferencia</strong>
   <label>Origen<select name="from_location_id" required>
    <option value="">Selecciona…</option>
    {activeLocations.map(l=><option key={l.id} value={l.id}>{locationLabel(l.id)}</option>)}
   </select></label>
   <label>Destino<select name="to_location_id" required>
    <option value="">Selecciona…</option>
    {activeLocations.map(l=><option key={l.id} value={l.id}>{locationLabel(l.id)}</option>)}
   </select></label>
   <label>ID del Variant<input name="variant_id" placeholder="uuid del variant" required/></label>
   <label>Cantidad<input name="quantity" type="number" min={1} required/></label>
   <label>Motivo<input name="reason" maxLength={500}/></label>
   <button>Crear transferencia</button>
  </form>}
  {loading?<p>Cargando…</p>:items.length===0?<EmptyState title="Sin transferencias" description="Crea una para mover stock entre Locations."/>:items.map(item=>
   <div className="row" key={item.id}>
    <span>
     <strong>{item.quantity} uds</strong> · {item.status}<br/>
     {locationLabel(item.from_location_id)} → {locationLabel(item.to_location_id)}<br/>
     Variant {item.variant_id}
    </span>
    {canManage&&item.status==="in_transit"&&<div className="nav">
     <button className="compact" onClick={()=>complete(item)}>Completar</button>
     <button className="compact" onClick={()=>cancel(item)}>Cancelar</button>
    </div>}
   </div>
  )}
  {error&&<p className="error" role="alert">{error}</p>}
 </AdminShell>;
}
