"use client";
import{FormEvent,useEffect,useState}from"react";import{useParams}from"next/navigation";
import{Shell}from"@/components/Shell";
import{activeStore,listStores,selectStore,Store}from"@/lib/platform";
import{Attribute,AttributeOption,Category,catalogCommand,catalogContext,catalogCreate,catalogGet,catalogPage,catalogUpdate,Option,OptionValue,ProductAttributeValue,ProductAttributeValueOption,ProductDetail,ProductOption,ProductTypeAttribute,Taxonomy,technicalError,Variant,VariantOptionValue}from"@/lib/catalog";

export default function Page(){const params=useParams<{id:string}>(),productId=params.id;const[detail,setDetail]=useState<ProductDetail|null>(null),[permissions,setPermissions]=useState<string[]>([]),[stores,setStores]=useState<Store[]>([]),[storeId,setStoreId]=useState(activeStore()??""),[categories,setCategories]=useState<Category[]>([]),[error,setError]=useState(""),[loading,setLoading]=useState(true);const[options,setOptions]=useState<Option[]>([]),[productOptions,setProductOptions]=useState<ProductOption[]>([]),[valuesByOption,setValuesByOption]=useState<Record<string,OptionValue[]>>({});const[attributes,setAttributes]=useState<Attribute[]>([]),[productTypeAttributes,setProductTypeAttributes]=useState<ProductTypeAttribute[]>([]),[attributeOptions,setAttributeOptions]=useState<Record<string,AttributeOption[]>>({}),[attributeValues,setAttributeValues]=useState<ProductAttributeValue[]>([]),[attributeValueOptions,setAttributeValueOptions]=useState<ProductAttributeValueOption[]>([]);const canUpdate=permissions.includes("catalog.product.update"),canVariant=permissions.includes("catalog.variant.update"),canCreateVariant=permissions.includes("catalog.variant.create"),canArchive=permissions.includes("catalog.product.archive"),canAssign=permissions.includes("catalog.assignment.manage"),canCategory=permissions.includes("catalog.assignment.manage"),canManageProductOptions=permissions.includes("catalog.product_option.manage"),canManageSpecs=permissions.includes("catalog.product_attribute_value.manage");

async function load(){
 setLoading(true);
 try{
  const[value,ctx,storeRows,taxonomyPage,optionPage,attributePage]=await Promise.all([catalogGet<ProductDetail>(`/products/${productId}`),catalogContext(),listStores(),catalogPage<Taxonomy>("/taxonomies"),catalogPage<Option>("/options"),catalogPage<Attribute>("/attributes")]);
  const categoryRows=(await Promise.all(taxonomyPage.items.map(item=>catalogGet<Category[]>(`/taxonomies/${item.id}/categories`)))).flat();
  const activeOptions=optionPage.items.filter(item=>item.status!=="archived");
  const assigned=await catalogGet<ProductOption[]>(`/products/${productId}/options`);
  const activeAssigned=assigned.filter(item=>!item.archived_at);
  const valuePairs=await Promise.all(activeAssigned.map(async item=>[item.option_id,await catalogGet<OptionValue[]>(`/options/${item.option_id}/values`)] as const));

  const activeAttributes=attributePage.items.filter(item=>item.status!=="archived");
  const typeAttributes=(await catalogGet<ProductTypeAttribute[]>(`/product-types/${value.product.product_type_id}/attributes`)).filter(item=>!item.archived_at);
  const selectable=typeAttributes.filter(entry=>{const attribute=activeAttributes.find(a=>a.id===entry.attribute_id);return attribute&&(attribute.data_type==="SELECT"||attribute.data_type==="MULTI_SELECT")});
  const attributeOptionPairs=await Promise.all(selectable.map(async entry=>[entry.attribute_id,await catalogGet<AttributeOption[]>(`/attributes/${entry.attribute_id}/options`)] as const));
  const[specValues,specValueOptions]=await Promise.all([catalogGet<ProductAttributeValue[]>(`/products/${productId}/attributes`),catalogGet<ProductAttributeValueOption[]>(`/products/${productId}/attribute-value-options`)]);

  setDetail(value);setPermissions(ctx.permissions);setStores(storeRows);setCategories(categoryRows);setOptions(activeOptions);setProductOptions(activeAssigned);setValuesByOption(Object.fromEntries(valuePairs));
  setAttributes(activeAttributes);setProductTypeAttributes(typeAttributes);setAttributeOptions(Object.fromEntries(attributeOptionPairs));setAttributeValues(specValues);setAttributeValueOptions(specValueOptions);setError("");
 }catch(e){setError(technicalError(e))}finally{setLoading(false)}
}
useEffect(()=>{load()},[productId]);

function chooseStore(id:string){setStoreId(id);if(id)selectStore(id)}

async function productAction(action:"activate"|"archive"){if(!detail)return;try{await catalogCommand(`/products/${productId}/${action}`,detail.product.version);await load()}catch(e){setError(technicalError(e))}}

async function createVariant(event:FormEvent<HTMLFormElement>){
 event.preventDefault();
 const element=event.currentTarget,form=new FormData(element);
 const optionValueIds=productOptions.map(item=>form.get(`option-${item.option_id}`)).filter((value):value is string=>typeof value==="string"&&value.length>0);
 try{
  await catalogCreate(`/products/${productId}/variants`,optionValueIds.length>0?{sku:form.get("sku"),option_value_ids:optionValueIds}:{sku:form.get("sku")});
  element.reset();await load();
 }catch(e){setError(technicalError(e))}
}

async function updateVariant(variant:Variant,sku:string){try{await catalogUpdate(`/variants/${variant.id}`,{sku},variant.version);await load()}catch(e){setError(technicalError(e))}}
async function archiveVariant(variant:Variant){try{await catalogCommand(`/variants/${variant.id}/archive`,variant.version);await load()}catch(e){setError(technicalError(e))}}
async function assignStore(){if(!storeId)return;try{await catalogCreate(`/products/${productId}/stores/${storeId}`,{status:"draft"},"PUT");await load()}catch(e){setError(technicalError(e))}}
async function unassignStore(){const assignment=detail?.stores.find(item=>item.store_id===storeId);if(!assignment)return;try{await catalogCommand(`/products/${productId}/stores/${storeId}`,assignment.version,"DELETE");await load()}catch(e){setError(technicalError(e))}}
async function assignCategory(categoryId:string){if(!detail||!categoryId)return;const assignments=detail.categories.filter(item=>item.category_id!==categoryId).map(item=>({category_id:item.category_id,is_primary:item.is_primary,position:item.position}));assignments.push({category_id:categoryId,is_primary:assignments.length===0,position:assignments.length});try{await catalogUpdate(`/products/${productId}/categories`,{assignments},detail.product.version,"PUT");await load()}catch(e){setError(technicalError(e))}}

async function addProductOption(optionId:string){
 if(!detail||!optionId)return;
 const next=productOptions.map(item=>({option_id:item.option_id,position:item.position}));
 next.push({option_id:optionId,position:next.length});
 try{await catalogUpdate(`/products/${productId}/options`,{options:next},detail.product.version,"PUT");await load()}catch(e){setError(technicalError(e))}
}
async function removeProductOption(optionId:string){
 if(!detail)return;
 const next=productOptions.filter(item=>item.option_id!==optionId).map(item=>({option_id:item.option_id,position:item.position}));
 try{await catalogUpdate(`/products/${productId}/options`,{options:next},detail.product.version,"PUT");await load()}catch(e){setError(technicalError(e))}
}

async function saveSpecifications(event:FormEvent<HTMLFormElement>){
 event.preventDefault();
 if(!detail)return;
 const element=event.currentTarget,form=new FormData(element);
 const values:{attribute_id:string;value:unknown}[]=[];
 for(const entry of productTypeAttributes){
  const attribute=attributes.find(a=>a.id===entry.attribute_id);
  if(!attribute)continue;
  if(attribute.data_type==="MULTI_SELECT"){
   const selected=form.getAll(`spec-${attribute.id}`).map(String).filter(Boolean);
   if(selected.length>0)values.push({attribute_id:attribute.id,value:selected});
   continue;
  }
  const raw=form.get(`spec-${attribute.id}`);
  if(attribute.data_type==="BOOLEAN"){values.push({attribute_id:attribute.id,value:raw==="on"});continue}
  if(raw===null||raw==="")continue;
  if(attribute.data_type==="INTEGER"){values.push({attribute_id:attribute.id,value:parseInt(String(raw),10)});continue}
  if(attribute.data_type==="DATETIME"){values.push({attribute_id:attribute.id,value:`${raw}:00Z`});continue}
  values.push({attribute_id:attribute.id,value:String(raw)});
 }
 try{
  await catalogUpdate(`/products/${productId}/attributes`,{values},detail.product.version,"PUT");
  await load();
 }catch(e){setError(technicalError(e))}
}

return <Shell title="Detalle de producto">{loading&&!detail?<p>Cargando…</p>:detail&&<>
 <div className="tile">
  <strong>{detail.translations[0]?.name??detail.product.code??detail.product.id}</strong>
  <p>{detail.product.status} · v{detail.product.version} · activo no significa publicado</p>
  <div className="nav">
   {canUpdate&&detail.product.status==="draft"&&<button className="compact" onClick={()=>productAction("activate")}>Activar</button>}
   {canArchive&&detail.product.status!=="archived"&&<button className="compact" onClick={()=>productAction("archive")}>Archivar</button>}
   <button className="compact" onClick={load}>Recargar</button>
  </div>
 </div>

 <h2>Opciones</h2>
 {productOptions.length===0?<p>Este Product no tiene Options asignadas. Sin Options, sus Variants no tienen combinación.</p>:productOptions.map(item=>
  <div className="row" key={item.option_id}>
   <span>{options.find(option=>option.id===item.option_id)?.name??item.option_id}{item.required?" · requerida":""}</span>
   {canManageProductOptions&&detail.product.status!=="archived"&&<button className="compact" onClick={()=>removeProductOption(item.option_id)}>Quitar</button>}
  </div>
 )}
 {canManageProductOptions&&detail.product.status!=="archived"&&<label>Agregar Option<select aria-label="Agregar Option" defaultValue="" onChange={event=>{addProductOption(event.target.value);event.target.value=""}}>
  <option value="">Selecciona</option>
  {options.filter(item=>!productOptions.some(assigned=>assigned.option_id===item.id)).map(item=><option key={item.id} value={item.id}>{item.name}</option>)}
 </select></label>}

 <h2>Variants</h2>
 {canCreateVariant&&detail.product.status!=="archived"&&<form className="tile" onSubmit={createVariant}>
  <label>Nuevo SKU<input name="sku" required/></label>
  {productOptions.map(item=><label key={item.option_id}>{options.find(option=>option.id===item.option_id)?.name??item.option_id}
   <select name={`option-${item.option_id}`} required>
    <option value="">Selecciona</option>
    {(valuesByOption[item.option_id]??[]).filter(value=>value.status!=="archived").map(value=><option key={value.id} value={value.id}>{value.value}</option>)}
   </select>
  </label>)}
  <button>Crear Variant</button>
 </form>}
 {detail.variants.map(variant=><VariantEditor key={variant.id} variant={variant} editable={canVariant&&variant.status!=="archived"} canArchive={permissions.includes("catalog.variant.archive")} options={options} valuesByOption={valuesByOption} onSave={updateVariant} onArchive={archiveVariant}/>) }

 <h2>Especificaciones</h2>
 {productTypeAttributes.length===0?<p>El Product Type de este Product no tiene Attributes asignados.</p>:<form className="tile" onSubmit={saveSpecifications}>
  {productTypeAttributes.map(entry=>{
   const attribute=attributes.find(a=>a.id===entry.attribute_id);
   if(!attribute)return null;
   const existing=attributeValues.find(v=>v.attribute_id===attribute.id);
   const label=`${attribute.name}${attribute.unit?` (${attribute.unit})`:""}${entry.required?" *":""}`;
   if(attribute.data_type==="BOOLEAN")return <label key={attribute.id}><input type="checkbox" name={`spec-${attribute.id}`} defaultChecked={existing?.value_boolean===true}/> {label}</label>;
   if(attribute.data_type==="LONG_TEXT")return <label key={attribute.id}>{label}<textarea name={`spec-${attribute.id}`} defaultValue={existing?.value_long_text??""}/></label>;
   if(attribute.data_type==="INTEGER")return <label key={attribute.id}>{label}<input type="number" step="1" name={`spec-${attribute.id}`} defaultValue={existing?.value_integer??""}/></label>;
   if(attribute.data_type==="DECIMAL")return <label key={attribute.id}>{label}<input type="number" step="any" name={`spec-${attribute.id}`} defaultValue={existing?.value_decimal??""}/></label>;
   if(attribute.data_type==="DATE")return <label key={attribute.id}>{label}<input type="date" name={`spec-${attribute.id}`} defaultValue={existing?.value_date??""}/></label>;
   if(attribute.data_type==="DATETIME")return <label key={attribute.id}>{label}<input type="datetime-local" name={`spec-${attribute.id}`} defaultValue={existing?.value_datetime?.slice(0,16)??""}/></label>;
   if(attribute.data_type==="SELECT")return <label key={attribute.id}>{label}<select name={`spec-${attribute.id}`} defaultValue={existing?.value_option_id??""}>
    <option value="">Sin valor</option>
    {(attributeOptions[attribute.id]??[]).filter(option=>option.status!=="archived").map(option=><option key={option.id} value={option.id}>{option.label}</option>)}
   </select></label>;
   if(attribute.data_type==="MULTI_SELECT"){
    const selectedIds=new Set(attributeValueOptions.filter(v=>v.attribute_id===attribute.id).map(v=>v.attribute_option_id));
    return <fieldset key={attribute.id}><legend>{label}</legend>
     {(attributeOptions[attribute.id]??[]).filter(option=>option.status!=="archived").map(option=><label key={option.id}><input type="checkbox" name={`spec-${attribute.id}`} value={option.id} defaultChecked={selectedIds.has(option.id)}/> {option.label}</label>)}
    </fieldset>;
   }
   return <label key={attribute.id}>{label}<input name={`spec-${attribute.id}`} defaultValue={existing?.value_text??""}/></label>;
  })}
  {canManageSpecs&&<button>Guardar especificaciones</button>}
 </form>}

 <h2>Category assignment</h2>
 {detail.categories.map(item=><p key={item.category_id}>{categories.find(category=>category.id===item.category_id)?.name??item.category_id}{item.is_primary?" · primary":""}</p>)}
 {canCategory&&detail.product.status!=="archived"&&<label>Agregar Category<select aria-label="Agregar Category" defaultValue="" onChange={event=>assignCategory(event.target.value)}><option value="">Selecciona</option>{categories.filter(item=>item.status!=="archived"&&!detail.categories.some(value=>value.category_id===item.id)).map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}

 <h2>Store assignment</h2>
 <label>Store<select aria-label="Store assignment" value={storeId} onChange={event=>chooseStore(event.target.value)}><option value="">Selecciona</option>{stores.filter(item=>item.status!=="archived").map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
 {storeId&&<p>{detail.stores.find(item=>item.store_id===storeId)?.status??"No asignado"}{detail.stores.find(item=>item.store_id===storeId)?.eligible?" · eligible":" · no eligible"}</p>}
 {canAssign&&storeId&&detail.product.status!=="archived"&&<div className="nav"><button className="compact" onClick={assignStore}>Asignar Store</button>{detail.stores.some(item=>item.store_id===storeId&&item.status!=="archived")&&<button className="compact" onClick={unassignStore}>Retirar Store</button>}</div>}
</>}{error&&<p className="error" role="alert">{error}</p>}</Shell>}

function VariantEditor({variant,editable,canArchive,options,valuesByOption,onSave,onArchive}:{variant:Variant;editable:boolean;canArchive:boolean;options:Option[];valuesByOption:Record<string,OptionValue[]>;onSave:(variant:Variant,sku:string)=>Promise<void>;onArchive:(variant:Variant)=>Promise<void>}){
 const[sku,setSku]=useState(variant.sku);
 const[combination,setCombination]=useState<VariantOptionValue[]>([]);
 useEffect(()=>{
  if(!variant.combination_fingerprint){setCombination([]);return}
  catalogGet<VariantOptionValue[]>(`/variants/${variant.id}/options`).then(setCombination).catch(()=>setCombination([]));
 },[variant.id,variant.combination_fingerprint]);
 function valueName(item:VariantOptionValue){return(valuesByOption[item.option_id]??[]).find(value=>value.id===item.option_value_id)?.value??item.option_value_id}
 return <div className="row">
  <span>
   <strong>{variant.is_default?"Default Variant":"Variant"}</strong><br/>
   {variant.status} · v{variant.version}
   {combination.length>0&&<><br/>{combination.map(item=>`${options.find(option=>option.id===item.option_id)?.name??item.option_id}: ${valueName(item)}`).join(" · ")}</>}
  </span>
  <span>
   {editable?<input aria-label={`SKU ${variant.sku}`} value={sku} onChange={event=>setSku(event.target.value)}/>:variant.sku}
   {editable&&sku!==variant.sku&&<button className="compact" onClick={()=>onSave(variant,sku)}>Guardar SKU</button>}
   {canArchive&&variant.status!=="archived"&&!variant.is_default&&<button className="compact" onClick={()=>onArchive(variant)}>Archivar</button>}
  </span>
 </div>
}
