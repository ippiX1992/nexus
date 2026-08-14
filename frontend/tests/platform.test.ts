import{beforeEach,describe,expect,it,vi}from"vitest";
import{ApiError,api,saveToken}from"../lib/api";
import{ACTIVE_STORE_CHANGED,activeStore,createResource,listStores,selectStore,updateResource}from"../lib/platform";

function json(value:unknown,status=200,headers:Record<string,string>={}){return new Response(JSON.stringify(value),{status,headers:{"Content-Type":"application/json",...headers}})}

describe("Platform Kernel client",()=>{
 beforeEach(()=>{sessionStorage.clear();saveToken("tenant-token");vi.restoreAllMocks()});
 it("lists and changes the active store",async()=>{vi.spyOn(globalThis,"fetch").mockResolvedValue(json([{id:"s1",name:"Main"}]));expect(await listStores()).toHaveLength(1);selectStore("s1");expect(activeStore()).toBe("s1");expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/stores"),expect.objectContaining({credentials:"include"}))});
 it("notifies the shell when the active store changes or clears",()=>{const listener=vi.fn();window.addEventListener(ACTIVE_STORE_CHANGED,listener);selectStore("secondary");selectStore(null);expect(listener).toHaveBeenCalledTimes(2);expect(activeStore()).toBeNull();window.removeEventListener(ACTIVE_STORE_CHANGED,listener)});
 it("creates resources with an idempotency key",async()=>{const mock=vi.spyOn(globalThis,"fetch").mockResolvedValue(json({id:"s1"},201));await createResource("/stores",{name:"Main"});const headers=mock.mock.calls[0][1]!.headers as Headers;expect(headers.get("Idempotency-Key")).toMatch(/.+/);expect(mock.mock.calls[0][1]!.method).toBe("POST")});
 it("updates resources with PATCH",async()=>{const mock=vi.spyOn(globalThis,"fetch").mockResolvedValue(json({id:"s2",name:"Secondary renamed"}));await updateResource("/stores/s2",{name:"Secondary renamed"});expect(mock).toHaveBeenCalledWith(expect.stringContaining("/stores/s2"),expect.objectContaining({method:"PATCH",body:JSON.stringify({name:"Secondary renamed"})}))});
 it("shows quota errors with their correlation id",async()=>{vi.spyOn(globalThis,"fetch").mockResolvedValue(json({detail:"Quota exceeded"},409,{"X-Correlation-ID":"correlation"}));try{await createResource("/stores",{})}catch(error){expect(error).toBeInstanceOf(ApiError);expect((error as ApiError).status).toBe(409);expect((error as ApiError).correlationId).toBe("correlation")}});
 it("surfaces insufficient permissions",async()=>{vi.spyOn(globalThis,"fetch").mockResolvedValue(json({detail:"Insufficient permissions"},403));await expect(api("/stores")).rejects.toThrow("Insufficient permissions")});
 it.each(["sites","channels","environments","markets"])("lists %s for the active store",async(kind)=>{vi.spyOn(globalThis,"fetch").mockResolvedValue(json([]));expect(await api(`/stores/s1/${kind}`)).toEqual([])});
 it("lists durable operations",async()=>{vi.spyOn(globalThis,"fetch").mockResolvedValue(json([{id:"o1",status:"succeeded"}]));expect(await api("/operations")).toEqual([{id:"o1",status:"succeeded"}])});
});
