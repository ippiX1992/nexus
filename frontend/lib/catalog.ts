import{ApiError,api}from"./api";

export type CatalogContext={permissions:string[]};
export type ProductType={id:string;code:string;name:string;description?:string;status:string;version:number};
export type Brand={id:string;code:string;name:string;slug:string;status:string;version:number};
export type Variant={id:string;product_id:string;sku:string;is_default:boolean;status:string;combination_fingerprint?:string|null;version:number};
export type Option={id:string;code:string;name:string;input_type:string;position:number;status:string;version:number};
export type OptionValue={id:string;option_id:string;code:string;value:string;swatch_hex?:string|null;position:number;status:string;version:number};
export type ProductOption={product_id:string;option_id:string;required:boolean;position:number;version:number};
export type Translation={id:string;locale:string;name:string;slug:string};
export type Product={id:string;product_type_id:string;brand_id?:string;code?:string;status:string;version:number;name?:string;default_sku?:string};
export type ProductStore={id:string;product_id:string;store_id:string;status:string;eligible:boolean;version:number};
export type ProductCategory={product_id:string;category_id:string;taxonomy_id:string;is_primary:boolean;position:number};
export type ProductDetail={product:Product;variants:Variant[];translations:Translation[];categories:ProductCategory[];stores:ProductStore[]};
export type Taxonomy={id:string;code:string;name:string;status:string;version:number};
export type Category={id:string;taxonomy_id:string;parent_id?:string;code:string;name:string;slug:string;position:number;status:string;version:number};
export type Page<T>={items:T[];next_cursor?:string;has_more:boolean};

export function technicalError(value:unknown){if(value instanceof ApiError)return`${value.message}${value.correlationId?` · ID ${value.correlationId}`:""}`;return value instanceof Error?value.message:"Error inesperado"}
export function catalogContext():Promise<CatalogContext>{return api("/me/context")}
export function catalogPage<T>(path:string):Promise<Page<T>>{return api(`/catalog${path}`)}
export function catalogGet<T>(path:string):Promise<T>{return api(`/catalog${path}`)}
export function catalogCreate<T>(path:string,payload:unknown,method="POST"):Promise<T>{return api(`/catalog${path}`,{method,headers:{"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify(payload)})}
export function catalogUpdate<T>(path:string,payload:unknown,version:number,method="PATCH"):Promise<T>{return api(`/catalog${path}`,{method,headers:{"If-Match":String(version)},body:JSON.stringify(payload)})}
export function catalogCommand<T>(path:string,version:number,method="POST"):Promise<T>{return api(`/catalog${path}`,{method,headers:{"If-Match":String(version)}})}
