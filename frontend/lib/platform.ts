import{api}from"./api";
export type Store={id:string;code:string;name:string;slug:string;status:string;default_locale:string;default_currency:string;timezone:string};
export function activeStore(){return typeof window!=="undefined"?sessionStorage.getItem("active_store_id"):null}
export function selectStore(id:string){sessionStorage.setItem("active_store_id",id)}
export function listStores():Promise<Store[]>{return api("/stores")}
export function createResource(path:string,payload:unknown){return api(path,{method:"POST",headers:{"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify(payload)})}
