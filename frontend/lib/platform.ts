import{api}from"./api";
export type Store={id:string;code:string;name:string;slug:string;status:string;default_locale:string;default_currency:string;timezone:string};
export const ACTIVE_STORE_CHANGED="nexus:active-store-changed";
export function activeStore(){return typeof window!=="undefined"?sessionStorage.getItem("active_store_id"):null}
export function selectStore(id:string|null){
 if(typeof window==="undefined")return;
 if(id)sessionStorage.setItem("active_store_id",id);else sessionStorage.removeItem("active_store_id");
 window.dispatchEvent(new CustomEvent(ACTIVE_STORE_CHANGED,{detail:{storeId:id}}));
}
export function listStores():Promise<Store[]>{return api("/stores")}
export function createResource(path:string,payload:unknown){return api(path,{method:"POST",headers:{"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify(payload)})}
export function updateResource(path:string,payload:unknown){return api(path,{method:"PATCH",body:JSON.stringify(payload)})}
