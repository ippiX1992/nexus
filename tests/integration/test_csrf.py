import pytest

pytestmark=pytest.mark.integration
async def test_refresh_requires_double_submit_and_allowed_origin(client,registration):
    await client.post("/api/v1/auth/register",json=registration); login=await client.post("/api/v1/auth/login",json={"email":registration["email"],"password":registration["password"]}); csrf=login.cookies["csrf_token"]
    assert (await client.post("/api/v1/auth/refresh")).status_code==403
    assert (await client.post("/api/v1/auth/refresh",headers={"Origin":"http://evil.test","X-CSRF-Token":csrf})).status_code==403
    assert (await client.post("/api/v1/auth/refresh",headers={"Origin":"http://testserver","X-CSRF-Token":"wrong"})).status_code==403
    assert (await client.post("/api/v1/auth/refresh",headers={"Origin":"http://testserver","X-CSRF-Token":csrf})).status_code==200
