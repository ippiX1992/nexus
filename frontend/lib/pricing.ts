import{ApiError,api}from"./api";

export type PriceList={id:string;code:string;name:string;currency_code:string;is_default:boolean;notes?:string|null;status:string;version:number;created_at:string};
export type PriceListEntry={id:string;price_list_id:string;variant_id:string;unit_amount:string;compare_at_amount?:string|null;msrp_amount?:string|null;cost_amount?:string|null;status:string;version:number};
export type ScopeType="store"|"channel"|"market";
export type Assignment={id:string;price_list_id:string;scope_type:ScopeType;store_id?:string|null;channel_id?:string|null;market_id?:string|null;priority:number;effective_from?:string|null;effective_until?:string|null;status:string;version:number};
export type Override={id:string;variant_id:string;scope_type:ScopeType;store_id?:string|null;channel_id?:string|null;market_id?:string|null;unit_amount:string;compare_at_amount?:string|null;currency_code:string;priority:number;effective_from?:string|null;effective_until?:string|null;reason?:string|null;status:string;version:number};
export type ResolvedPrice={source:"override"|"assignment"|"default";source_id:string;variant_id:string;unit_amount:string;compare_at_amount?:string|null;msrp_amount?:string|null;cost_amount?:string|null;currency_code:string;price_list_id?:string|null};
export type PriceHistoryEntry={id:string;entity_type:string;entity_id:string;variant_id:string;field_name:string;previous_amount?:string|null;new_amount?:string|null;currency_code:string;changed_by?:string|null;changed_at:string;reason?:string|null};
export type Page<T>={items:T[];next_cursor?:string;has_more:boolean};

export function technicalError(value:unknown){if(value instanceof ApiError)return`${value.message}${value.correlationId?` · ID ${value.correlationId}`:""}`;return value instanceof Error?value.message:"Error inesperado"}
export function pricingPage<T>(path:string):Promise<Page<T>>{return api(`/pricing${path}`)}
export function pricingGet<T>(path:string):Promise<T>{return api(`/pricing${path}`)}
export function pricingCreate<T>(path:string,payload:unknown):Promise<T>{return api(`/pricing${path}`,{method:"POST",headers:{"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify(payload)})}
export function pricingPut<T>(path:string,payload:unknown):Promise<T>{return api(`/pricing${path}`,{method:"PUT",body:JSON.stringify(payload)})}
export function pricingUpdate<T>(path:string,payload:unknown,version:number):Promise<T>{return api(`/pricing${path}`,{method:"PATCH",headers:{"If-Match":String(version)},body:JSON.stringify(payload)})}
export function pricingCommand<T>(path:string,version:number):Promise<T>{return api(`/pricing${path}`,{method:"POST",headers:{"If-Match":String(version)}})}
