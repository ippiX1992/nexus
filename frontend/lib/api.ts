const API=process.env.NEXT_PUBLIC_API_URL??"http://localhost:8000/api/v1";
export class ApiError extends Error{constructor(message:string,public status:number,public correlationId?:string){super(message);this.name="ApiError"}}
export function token(){return typeof window!=="undefined"?sessionStorage.getItem("access_token"):null}
export function saveToken(value:string){sessionStorage.setItem("access_token",value)}
export function readCookie(name:string){return typeof document!=="undefined"?document.cookie.split("; ").find(v=>v.startsWith(`${name}=`))?.split("=")[1]:undefined}
async function request(path:string,options:RequestInit,retry:boolean){
 const headers=new Headers(options.headers);headers.set("Content-Type","application/json");const access=token();if(access)headers.set("Authorization",`Bearer ${access}`);
 if(options.method&&options.method!=="GET"){const csrf=readCookie("csrf_token");if(csrf)headers.set("X-CSRF-Token",decodeURIComponent(csrf))}
 const response=await fetch(`${API}${path}`,{...options,headers,credentials:"include"});
 if(response.status===401&&retry&&path!=="/auth/refresh"){const refreshed=await request("/auth/refresh",{method:"POST"},false);saveToken(refreshed.access_token);return request(path,options,false)}
 if(!response.ok){const body=await response.json().catch(()=>({}));throw new ApiError(body.detail??"No se pudo completar la solicitud",response.status,response.headers.get("X-Correlation-ID")??undefined)}
 return response.status===204?null:response.json()
}
export function api(path:string,options:RequestInit={}){return request(path,options,true)}
// Multipart upload: never set Content-Type by hand so the browser adds the
// multipart boundary. Reuses the same bearer token + CSRF as api().
export async function apiUpload(path:string,form:FormData){
 const headers=new Headers();const access=token();if(access)headers.set("Authorization",`Bearer ${access}`);
 const csrf=readCookie("csrf_token");if(csrf)headers.set("X-CSRF-Token",decodeURIComponent(csrf));
 const response=await fetch(`${API}${path}`,{method:"POST",body:form,headers,credentials:"include"});
 if(!response.ok){const body=await response.json().catch(()=>({}));throw new ApiError(body.detail??"No se pudo subir el archivo",response.status,response.headers.get("X-Correlation-ID")??undefined)}
 return response.status===204?null:response.json()
}
