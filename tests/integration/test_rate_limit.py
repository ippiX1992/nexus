import pytest

pytestmark=pytest.mark.integration
async def test_login_rate_limit_is_distributed_and_returns_retry_after(client,registration,monkeypatch):
    monkeypatch.setattr("app.core.rate_limit.time.time", lambda: 1_700_000_000.0)
    await client.post("/api/v1/auth/register",json=registration); payload={"email":registration["email"],"password":"bad-password"}
    for _ in range(10): assert (await client.post("/api/v1/auth/login",json=payload)).status_code==401
    limited=await client.post("/api/v1/auth/login",json=payload); assert limited.status_code==429 and limited.headers["Retry-After"]=="60"
    independent=await client.post("/api/v1/auth/login",json={"email":"another@example.com","password":"bad-password"}); assert independent.status_code==401
