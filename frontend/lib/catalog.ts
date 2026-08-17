import{ApiError,api}from"./api";

export type CatalogContext={permissions:string[]};
export type ProductType={id:string;code:string;name:string;description?:string;status:string;version:number};
export type Brand={id:string;code:string;name:string;slug:string;status:string;version:number};
export type Variant={id:string;product_id:string;sku:string;is_default:boolean;status:string;combination_fingerprint?:string|null;version:number};
export type Option={id:string;code:string;name:string;input_type:string;position:number;status:string;version:number};
export type OptionValue={id:string;option_id:string;code:string;value:string;swatch_hex?:string|null;position:number;status:string;version:number};
export type ProductOption={product_id:string;option_id:string;required:boolean;position:number;version:number;archived_at?:string|null};
export type VariantOptionValue={variant_id:string;product_id:string;option_id:string;option_value_id:string};
export type AttributeDataType="TEXT"|"LONG_TEXT"|"INTEGER"|"DECIMAL"|"BOOLEAN"|"DATE"|"DATETIME"|"SELECT"|"MULTI_SELECT";
export type Attribute={id:string;code:string;name:string;description?:string|null;data_type:AttributeDataType;unit?:string|null;is_required:boolean;is_filterable:boolean;is_searchable:boolean;is_comparable:boolean;is_visible_storefront:boolean;position:number;status:string;version:number};
export type AttributeOption={id:string;attribute_id:string;code:string;label:string;position:number;status:string;version:number};
export type AttributeGroup={id:string;code:string;name:string;description?:string|null;position:number;status:string;version:number};
export type ProductTypeAttribute={product_type_id:string;attribute_id:string;group_id?:string|null;position:number;required:boolean;visible_override?:boolean|null;filterable_override?:boolean|null;comparable_override?:boolean|null;version:number;archived_at?:string|null};
export type ProductAttributeValue={product_id:string;attribute_id:string;value_text?:string|null;value_long_text?:string|null;value_integer?:number|null;value_decimal?:string|null;value_boolean?:boolean|null;value_date?:string|null;value_datetime?:string|null;value_option_id?:string|null;version:number};
export type ProductAttributeValueOption={product_id:string;attribute_id:string;attribute_option_id:string};
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

// Resolve variant ids -> "Product name · SKU" for modules that key on variant
// (Pricing, Inventory). The proper long-term solution is a batched backend
// lookup (GET /catalog/variants?ids=...); this frontend resolver fetches the
// product list and each product's variants so those admin screens can show a
// human label instead of a raw UUID. Adequate for tenant-scale catalogs shown
// in the admin; if it becomes a hot path, promote it to a backend read model.
export async function variantLabels():Promise<Map<string,string>>{
 // Single batched backend lookup (GET /catalog/variant-labels) returns every
 // default variant's "Product name · SKU" label — scales to the full catalog
 // without a detail request per product and without falling back to raw UUIDs.
 const rows=await api("/catalog/variant-labels") as {variant_id:string;label:string}[];
 return new Map(rows.map(r=>[r.variant_id,r.label]));
}
