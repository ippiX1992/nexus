import{ApiError,api}from"./api";

export type Warehouse={id:string;code:string;name:string;country_code?:string|null;status:string;version:number;created_at:string};
export type Location={id:string;warehouse_id:string;code:string;name:string;location_type:string;status:string;version:number};
export type StockLevel={id:string;location_id:string;variant_id:string;on_hand:number;reserved:number;incoming:number;available:number;version:number};
export type LedgerEntry={id:string;location_id:string;variant_id:string;entry_type:string;quantity_delta:number;on_hand_after:number;reason?:string|null;reference_type?:string|null;reference_id?:string|null;created_at:string};
export type Transfer={id:string;from_location_id:string;to_location_id:string;variant_id:string;quantity:number;reason?:string|null;status:string;version:number;created_at:string};
export type ScopeType="store"|"channel"|"market";
export type Reservation={id:string;variant_id:string;location_id:string;quantity:number;scope_type?:string|null;status:string;version:number;expires_at?:string|null};
export type FulfillmentScope={id:string;warehouse_id:string;scope_type:ScopeType;store_id?:string|null;channel_id?:string|null;market_id?:string|null;priority:number;status:string;version:number};
export type AllocationLine={location_id:string;warehouse_id:string;quantity:number};
export type AllocationPlan={requested:number;allocated:number;shortfall:number;fully_allocated:boolean;allocations:AllocationLine[]};
export type Page<T>={items:T[];next_cursor?:string;has_more:boolean};

export function technicalError(value:unknown){if(value instanceof ApiError)return`${value.message}${value.correlationId?` · ID ${value.correlationId}`:""}`;return value instanceof Error?value.message:"Error inesperado"}
export function inventoryPage<T>(path:string):Promise<Page<T>>{return api(`/inventory${path}`)}
export function inventoryGet<T>(path:string):Promise<T>{return api(`/inventory${path}`)}
export function inventoryCreate<T>(path:string,payload:unknown):Promise<T>{return api(`/inventory${path}`,{method:"POST",headers:{"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify(payload)})}
export function inventoryAction<T>(path:string,payload:unknown):Promise<T>{return api(`/inventory${path}`,{method:"POST",body:JSON.stringify(payload)})}
export function inventoryCommand<T>(path:string,version:number):Promise<T>{return api(`/inventory${path}`,{method:"POST",headers:{"If-Match":String(version)}})}
