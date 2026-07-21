import{beforeEach,describe,expect,it,vi}from"vitest";
import{saveToken}from"../lib/api";
import{pricingCommand,pricingCreate,pricingGet,pricingPage,pricingPut,pricingUpdate,technicalError}from"../lib/pricing";
import{ApiError}from"../lib/api";

function json(value:unknown,status=200,headers:Record<string,string>={}){return new Response(JSON.stringify(value),{status,headers:{"Content-Type":"application/json",...headers}})}

describe("Pricing Engine client",()=>{
 beforeEach(()=>{sessionStorage.clear();saveToken("tenant-token");vi.restoreAllMocks()});

 it("pages price lists under the /pricing prefix",async()=>{
  vi.spyOn(globalThis,"fetch").mockResolvedValue(json({items:[{id:"pl1"}],next_cursor:null,has_more:false}));
  const page=await pricingPage("/price-lists");
  expect(page.items).toHaveLength(1);
  expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/pricing/price-lists"),expect.objectContaining({credentials:"include"}));
 });

 it("gets a single price list",async()=>{
  vi.spyOn(globalThis,"fetch").mockResolvedValue(json({id:"pl1",code:"default"}));
  expect(await pricingGet("/price-lists/pl1")).toEqual({id:"pl1",code:"default"});
 });

 it("creates resources with an idempotency key and POST",async()=>{
  const mock=vi.spyOn(globalThis,"fetch").mockResolvedValue(json({id:"pl1"},201));
  await pricingCreate("/price-lists",{code:"default",name:"Default",currency_code:"USD"});
  const headers=mock.mock.calls[0][1]!.headers as Headers;
  expect(headers.get("Idempotency-Key")).toMatch(/.+/);
  expect(mock.mock.calls[0][1]!.method).toBe("POST");
 });

 it("upserts an entry with PUT and no concurrency header",async()=>{
  const mock=vi.spyOn(globalThis,"fetch").mockResolvedValue(json({id:"e1",unit_amount:"10.00"}));
  await pricingPut("/price-lists/pl1/entries/v1",{unit_amount:"10.00"});
  expect(mock.mock.calls[0][1]!.method).toBe("PUT");
  const headers=mock.mock.calls[0][1]!.headers as Headers;
  expect(headers.has("If-Match")).toBe(false);
 });

 it("updates with If-Match carrying the expected version",async()=>{
  const mock=vi.spyOn(globalThis,"fetch").mockResolvedValue(json({id:"pl1",version:2}));
  await pricingUpdate("/price-lists/pl1",{name:"New name"},1);
  const headers=mock.mock.calls[0][1]!.headers as Headers;
  expect(headers.get("If-Match")).toBe("1");
  expect(mock.mock.calls[0][1]!.method).toBe("PATCH");
 });

 it("sends archive commands with If-Match", async()=>{
  const mock=vi.spyOn(globalThis,"fetch").mockResolvedValue(json({id:"pl1",status:"archived"}));
  await pricingCommand("/price-lists/pl1/archive",3);
  const headers=mock.mock.calls[0][1]!.headers as Headers;
  expect(headers.get("If-Match")).toBe("3");
  expect(mock.mock.calls[0][1]!.method).toBe("POST");
 });

 it("surfaces a version conflict with its correlation id",async()=>{
  vi.spyOn(globalThis,"fetch").mockResolvedValue(json({detail:"Version conflict"},409,{"X-Correlation-ID":"corr-1"}));
  try{
   await pricingCommand("/price-lists/pl1/archive",1);
   throw new Error("expected pricingCommand to reject");
  }catch(error){
   expect(error).toBeInstanceOf(ApiError);
   expect((error as ApiError).status).toBe(409);
   expect(technicalError(error)).toContain("corr-1");
  }
 });

 it("surfaces a 404 when nothing resolves for a variant",async()=>{
  vi.spyOn(globalThis,"fetch").mockResolvedValue(json({detail:"No price is configured for this Variant in the given scope"},404));
  await expect(pricingGet("/resolve?variant_id=v1")).rejects.toThrow(/No price is configured/);
 });
});
