from datetime import UTC, datetime, timedelta

from sqlalchemy import update

IPHONE = {"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X)"}


async def create(client, **body):
    r = await client.post("/api/links", json={"url": "https://donstu.ru/abitur/", **body})
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_and_follow(client):
    link = await create(client)
    assert link["short_url"] == f"https://sho.rt/{link['code']}"
    assert len(link["code"]) == 7

    r = await client.get(f"/{link['code']}")
    assert r.status_code == 302
    assert r.headers["location"] == "https://donstu.ru/abitur/"


async def test_unknown_code_is_404(client):
    assert (await client.get("/nope123")).status_code == 404


async def test_custom_alias_and_conflict(client):
    link = await create(client, alias="abitur")
    assert link["code"] == "abitur"
    r = await client.post("/api/links", json={"url": "https://example.com", "alias": "abitur"})
    assert r.status_code == 409


async def test_reserved_alias_rejected(client):
    r = await client.post("/api/links", json={"url": "https://example.com", "alias": "docs"})
    assert r.status_code == 422


async def test_bad_url_explains_why(client):
    r = await client.post("/api/links", json={"url": "javascript:alert(1)"})
    assert r.status_code == 422
    assert "http" in r.json()["detail"]


async def test_stats_count_people_and_bots_separately(client):
    link = await create(client)
    code, token = link["code"], link["manage_token"]
    await client.get(f"/{code}", headers={**IPHONE, "referer": "https://vk.com/wall-1_2"})
    await client.get(f"/{code}", headers=IPHONE)
    await client.get(f"/{code}", headers={"user-agent": "TelegramBot (like TwitterBot)"})

    r = await client.get(f"/api/links/{code}/stats", headers={"x-manage-token": token})
    assert r.status_code == 200
    stats = r.json()
    assert stats["clicks_total"] == 3
    assert stats["clicks_by_people"] == 2
    assert stats["last_30_days"][-1]["clicks"] == 2
    assert len(stats["last_30_days"]) == 30
    assert {"name": "vk.com", "clicks": 1} in stats["referrers"]
    assert {"name": "mobile", "clicks": 2} in stats["devices"]


async def test_stats_need_the_token(client):
    link = await create(client)
    for headers in ({}, {"x-manage-token": "wrong"}):
        r = await client.get(f"/api/links/{link['code']}/stats", headers=headers)
        assert r.status_code == 404


async def test_delete_removes_link_and_cache(client):
    link = await create(client)
    code = link["code"]
    assert (await client.get(f"/{code}")).status_code == 302  # now cached
    r = await client.delete(f"/api/links/{code}", headers={"x-manage-token": link["manage_token"]})
    assert r.status_code == 204
    assert (await client.get(f"/{code}")).status_code == 404


async def test_expired_link_is_gone(client):
    from app.models import Link

    link = await create(client, expires_in_days=1)
    app = client._transport.app
    async with app.state.db.sessions() as s:
        await s.execute(update(Link).where(Link.code == link["code"]).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
        await s.commit()
    assert (await client.get(f"/{link['code']}")).status_code == 410


async def test_rate_limit_on_creation(client):
    for _ in range(5):
        await create(client)
    r = await client.post("/api/links", json={"url": "https://example.com"})
    assert r.status_code == 429


async def test_index_page(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert "<form" in r.text
