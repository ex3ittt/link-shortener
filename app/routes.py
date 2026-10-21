from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import codes
from app.cache import Cache
from app.config import Settings
from app.db import Database
from app.models import Click, Link
from app.schemas import CreateLink, DayCount, LinkCreated, LinkStats, NameCount
from app.useragent import device, referrer_host

router = APIRouter()


def settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def cache_dep(request: Request) -> Cache:
    return request.app.state.cache


async def session_dep(request: Request):
    db: Database = request.app.state.db
    async for session in db.session():
        yield session


SessionDep = Annotated[AsyncSession, Depends(session_dep)]
SettingsDep = Annotated[Settings, Depends(settings_dep)]
CacheDep = Annotated[Cache, Depends(cache_dep)]


def now() -> datetime:
    return datetime.now(UTC)


def as_utc(dt: datetime | None) -> datetime | None:
    # SQLite hands back naive datetimes even for timezone=True columns.
    return dt.replace(tzinfo=UTC) if dt is not None and dt.tzinfo is None else dt


@router.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/api/links", status_code=status.HTTP_201_CREATED, response_model=LinkCreated)
async def create_link(body: CreateLink, request: Request, session: SessionDep, settings: SettingsDep, cache: CacheDep) -> LinkCreated:
    client = request.client.host if request.client else "unknown"
    if not await cache.allow(f"create:{client}", settings.create_limit_per_minute, 60):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Слишком много ссылок подряд, подожди минуту")

    try:
        url = codes.normalize_url(body.url, urlsplit(settings.base_url).hostname or "")
    except codes.BadUrl as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None

    if body.alias is not None and not codes.is_valid_alias(body.alias):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Псевдоним: 3–32 символа, латиница, цифры, - и _")

    token = codes.new_token()
    expires_at = now() + timedelta(days=body.expires_in_days) if body.expires_in_days else None

    # Random codes collide rarely (57^7 ≈ 2·10^12), but the unique index is the
    # source of truth, so just retry on conflict instead of checking first.
    for _ in range(5):
        code = body.alias or codes.random_code(settings.code_length)
        link = Link(code=code, url=url, token_hash=codes.hash_token(token), expires_at=expires_at, clicks_total=0)
        session.add(link)
        try:
            await session.commit()
            break
        except IntegrityError:
            await session.rollback()
            if body.alias:
                raise HTTPException(status.HTTP_409_CONFLICT, "Такой псевдоним уже занят") from None
    else:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Не удалось подобрать свободный код")

    return LinkCreated(
        code=code,
        short_url=f"{settings.base_url.rstrip('/')}/{code}",
        url=url,
        expires_at=expires_at,
        manage_token=token,
    )


async def find_link(session: AsyncSession, code: str) -> Link:
    link = await session.scalar(select(Link).where(Link.code == code))
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Такой ссылки нет")
    return link


def check_token(link: Link, token: str | None) -> None:
    if token is None or not codes.tokens_match(token, link.token_hash):
        # 404, not 403: don't confirm that a code exists to someone guessing.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Такой ссылки нет")


@router.get("/api/links/{code}/stats", response_model=LinkStats)
async def link_stats(code: str, session: SessionDep, x_manage_token: Annotated[str | None, Header()] = None) -> LinkStats:
    link = await find_link(session, code)
    check_token(link, x_manage_token)

    since = now() - timedelta(days=30)
    rows = (await session.execute(select(Click.at, Click.referrer, Click.device).where(Click.link_id == link.id))).all()

    by_day = Counter(as_utc(at).date() for at, _, dev in rows if as_utc(at) >= since and dev != "bot")
    today = now().date()
    days = [today - timedelta(days=d) for d in range(29, -1, -1)]

    return LinkStats(
        code=link.code,
        url=link.url,
        created_at=as_utc(link.created_at),
        expires_at=as_utc(link.expires_at),
        clicks_total=link.clicks_total,
        clicks_by_people=sum(1 for *_, dev in rows if dev != "bot"),
        last_30_days=[DayCount(day=d, clicks=by_day.get(d, 0)) for d in days],
        referrers=[NameCount(name=n, clicks=c) for n, c in Counter(r or "напрямую" for _, r, dev in rows if dev != "bot").most_common(10)],
        devices=[NameCount(name=n, clicks=c) for n, c in Counter(dev for *_, dev in rows).most_common()],
    )


@router.delete("/api/links/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(code: str, session: SessionDep, cache: CacheDep, x_manage_token: Annotated[str | None, Header()] = None) -> None:
    link = await find_link(session, code)
    check_token(link, x_manage_token)
    await session.execute(delete(Click).where(Click.link_id == link.id))
    await session.delete(link)
    await session.commit()
    await cache.delete(code)


async def record_click(db: Database, link_id: int, referrer: str | None, dev: str) -> None:
    async with db.sessions() as session:
        session.add(Click(link_id=link_id, at=now(), referrer=referrer, device=dev))
        # Atomic increment in SQL — two simultaneous clicks can't lose one.
        await session.execute(update(Link).where(Link.id == link_id).values(clicks_total=Link.clicks_total + 1))
        await session.commit()


@router.get("/{code}", include_in_schema=False)
async def follow(code: str, request: Request, background: BackgroundTasks, session: SessionDep, settings: SettingsDep, cache: CacheDep) -> RedirectResponse:
    hit = await cache.get(code)
    if hit is None:
        link = await session.scalar(select(Link).where(Link.code == code))
        if link is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Такой ссылки нет")
        expires = as_utc(link.expires_at)
        hit = {"id": link.id, "url": link.url, "exp": expires.timestamp() if expires else None}
        ttl = settings.cache_ttl_seconds
        if expires:
            ttl = max(1, min(ttl, int(expires.timestamp() - now().timestamp())))
        await cache.set(code, hit, ttl)

    if hit["exp"] is not None and hit["exp"] <= now().timestamp():
        raise HTTPException(status.HTTP_410_GONE, "Срок действия ссылки истёк")

    # The redirect goes out first; the click is written after the response.
    background.add_task(
        record_click,
        request.app.state.db,
        hit["id"],
        referrer_host(request.headers.get("referer")),
        device(request.headers.get("user-agent")),
    )
    # 302, not 301: browsers cache 301 forever and later clicks would bypass us.
    return RedirectResponse(hit["url"], status_code=status.HTTP_302_FOUND)
