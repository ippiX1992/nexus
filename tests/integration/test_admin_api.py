import pytest

pytestmark=pytest.mark.integration
async def owner_context(client,registration):
    registered=await client.post("/api/v1/auth/register",json=registration); tenant=registered.json()["tenant"]
    login=await client.post("/api/v1/auth/login",json={"email":registration["email"],"password":registration["password"]}); access=login.json()["access_token"]
    selected=await client.post("/api/v1/auth/select-tenant",headers={"Authorization":f"Bearer {access}"},json={"tenant_id":tenant["id"]}); return {"Authorization":f"Bearer {selected.json()['access_token']}"},tenant
async def test_role_crud_invitation_member_and_transfer(client,registration):
    headers,tenant=await owner_context(client,registration)
    permissions=(await client.get("/api/v1/permissions",headers=headers)).json(); assert "tenant.read" in permissions
    created=await client.post("/api/v1/roles",headers=headers,json={"name":"support","permissions":["tenant.read","member.read"]}); assert created.status_code==201
    role=created.json(); assert not role["is_system"]
    updated=await client.put(f"/api/v1/roles/{role['id']}/permissions",headers=headers,json={"permissions":["tenant.read"]}); assert updated.status_code==200
    invite=await client.post("/api/v1/members/invitations",headers=headers,json={"email":"member@example.com","role_ids":[role["id"]]}); assert invite.status_code==201
    token=invite.json()["invitation_token"]
    assert (await client.post("/api/v1/members/invitations/accept",json={"token":token,"password":"Member-Secure-99","full_name":"Member Two"})).status_code==200
    members=(await client.get("/api/v1/members",headers=headers)).json(); assert len(members)==2
    owner=next(m for m in members if "owner" in m["roles"]); target=next(m for m in members if m["email"]=="member@example.com")
    assert (await client.patch(f"/api/v1/members/{owner['membership_id']}",headers=headers,json={"is_active":False})).status_code==409
    assert (await client.delete(f"/api/v1/roles/{role['id']}",headers=headers)).status_code==204
    csrf_headers={**headers,"Origin":"http://testserver","X-CSRF-Token":client.cookies["csrf_token"]}; transfer=await client.post("/api/v1/tenant/transfer-ownership",headers=csrf_headers,json={"target_membership_id":target["membership_id"],"password":registration["password"]}); assert transfer.status_code==204
async def test_cross_tenant_role_assignment_is_rejected(client,registration):
    headers,_=await owner_context(client,registration)
    other={**registration,"email":"other@example.com","company":"Other Tenant"}; other_headers,_=await owner_context(client,other)
    foreign=(await client.get("/api/v1/roles",headers=other_headers)).json()[0]
    member=(await client.get("/api/v1/members",headers=headers)).json()[0]
    response=await client.put(f"/api/v1/members/{member['membership_id']}/roles",headers=headers,json={"role_ids":[foreign["id"]]}); assert response.status_code==400

async def test_admin_guards_resend_cancel_and_custom_role_update(client,registration):
    headers,_=await owner_context(client,registration)
    roles=(await client.get("/api/v1/roles",headers=headers)).json(); owner=next(r for r in roles if r["name"]=="owner"); viewer=next(r for r in roles if r["name"]=="viewer")
    assert (await client.patch(f"/api/v1/roles/{owner['id']}",headers=headers,json={"name":"changed"})).status_code==400
    assert (await client.delete(f"/api/v1/roles/{owner['id']}",headers=headers)).status_code==400
    assert (await client.post("/api/v1/roles",headers=headers,json={"name":"badperm","permissions":["unknown.permission"]})).status_code==400
    created=(await client.post("/api/v1/roles",headers=headers,json={"name":"temporary","permissions":["tenant.read"]})).json()
    assert (await client.get(f"/api/v1/roles/{created['id']}",headers=headers)).status_code==200
    renamed=await client.patch(f"/api/v1/roles/{created['id']}",headers=headers,json={"name":"renamed"}); assert renamed.status_code==200 and renamed.json()["name"]=="renamed"
    invite=await client.post("/api/v1/members/invitations",headers=headers,json={"email":"cancel@example.com","role_ids":[viewer["id"]]}); iid=invite.json()["id"]
    assert (await client.post("/api/v1/members/invitations",headers=headers,json={"email":"cancel@example.com","role_ids":[]})).status_code==409
    resent=await client.post(f"/api/v1/members/invitations/{iid}/resend",headers=headers); token=resent.json()["invitation_token"]; assert resent.status_code==200
    assert (await client.delete(f"/api/v1/members/invitations/{iid}",headers=headers)).status_code==204
    assert (await client.post("/api/v1/members/invitations/accept",json={"token":token,"password":"Cancel-Secure-99","full_name":"Cancelled"})).status_code==400
    member=(await client.get("/api/v1/members",headers=headers)).json()[0]
    assert (await client.put(f"/api/v1/members/{member['membership_id']}/roles",headers=headers,json={"role_ids":[]})).status_code==409
    assert (await client.delete(f"/api/v1/members/{member['membership_id']}",headers=headers)).status_code==409
