import{beforeEach,describe,expect,it,vi}from"vitest";
import{ApiError,saveToken}from"../lib/api";
import{inventoryAction,inventoryCommand,inventoryCreate,inventoryGet,inventoryPage,technicalError}from"../lib/inventory";

function json(value:unknown,status=200,headers:Record<string,string>={}){return new Response(JSON.stringify(value),{status,headers:{"Content-Type":"application/json",...headers}})}

describe("Inventory Engine client",()=>{
 beforeEach(()=>{sessionStorage.clear();saveToken("tenant-token");vi.restoreAllMocks()});

 it("pages stock under the /inventory prefix",async()=>{
  vi.spyOn(globalThis,"fetch").mockResolvedValue(json({items:[{id:"s1"}],next_cursor:null,has_more:false}));
  const page=await inventoryPage("/stock");
  expect(page.items).toHaveLength(1);
  expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/inventory/stock"),expect.objectContaining({credentials:"include"}));
 });

 it("gets a single warehouse",async()=>{
  vi.spyOn(globalThis,"fetch").mockResolvedValue(json({id:"w1",code:"wh"}));
  expect(await inventoryGet("/warehouses/w1")).toEqual({id:"w1",code:"wh"});
 });

 it("creates warehouses with an idempotency key and POST",async()=>{
  const mock=vi.spyOn(globalThis,"fetch").mockResolvedValue(json({id:"w1"},201));
  await inventoryCreate("/warehouses",{code:"wh",name:"Main"});
  const headers=mock.mock.calls[0][1]!.headers as Headers;
  expect(headers.get("Idempotency-Key")).toMatch(/.+/);
  expect(mock.mock.calls[0][1]!.method).toBe("POST");
 });

 it("posts stock movements without a concurrency or idempotency header",async()=>{
  const mock=vi.spyOn(globalThis,"fetch").mockResolvedValue(json({id:"s1",on_hand:10}));
  await inventoryAction("/locations/l1/variants/v1/receive",{quantity:10});
  const headers=mock.mock.calls[0][1]!.headers as Headers;
  expect(mock.mock.calls[0][1]!.method).toBe("POST");
  expect(headers.has("If-Match")).toBe(false);
  expect(headers.has("Idempotency-Key")).toBe(false);
 });

 it("sends lifecycle commands with If-Match",async()=>{
  const mock=vi.spyOn(globalThis,"fetch").mockResolvedValue(json({id:"t1",status:"completed"}));
  await inventoryCommand("/transfers/t1/complete",2);
  const headers=mock.mock.calls[0][1]!.headers as Headers;
  expect(headers.get("If-Match")).toBe("2");
  expect(mock.mock.calls[0][1]!.method).toBe("POST");
 });

 it("surfaces insufficient-stock conflicts with their correlation id",async()=>{
  vi.spyOn(globalThis,"fetch").mockResolvedValue(json({detail:"Cannot reserve 5; only 3 available"},409,{"X-Correlation-ID":"corr-inv"}));
  try{
   await inventoryCreate("/reservations",{variant_id:"v1",quantity:5,scope_type:"channel",scope_id:"c1"});
   throw new Error("expected inventoryCreate to reject");
  }catch(error){
   expect(error).toBeInstanceOf(ApiError);
   expect((error as ApiError).status).toBe(409);
   expect(technicalError(error)).toContain("corr-inv");
  }
 });

 it("surfaces insufficient permissions",async()=>{
  vi.spyOn(globalThis,"fetch").mockResolvedValue(json({detail:"Insufficient permissions"},403));
  await expect(inventoryGet("/warehouses")).rejects.toThrow("Insufficient permissions");
 });
});
