"""Product media engine: upload/list/reorder/delete photos (and video embeds)
stored on local disk under settings.media_root and served at /media.

Tenant isolation is enforced by RLS: get_current_context (via require_permission)
sets app.current_tenant_id on the request-scoped session, and every write carries
the tenant_id, so the FORCE RLS policies gate every row.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_permission
from app.application.authorization import TenantContext
from app.core.config import get_settings
from app.infrastructure.database import get_session

router = APIRouter(prefix="/api/v1/catalog/products/{product_id}/media", tags=["catalog-media"])

_EXT_BY_TYPE = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/avif": "avif", "image/gif": "gif"}
_MAX_BYTES = 25 * 1024 * 1024  # 25 MB


def _media_root() -> Path:
    root = Path(get_settings().media_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _serialize(row) -> dict:
    url = f"/media/{row.storage_key}" if row.storage_key else row.external_url
    return {
        "id": str(row.id),
        "media_type": row.media_type,
        "url": url,
        "alt_text": row.alt_text,
        "position": row.position,
        "is_primary": row.is_primary,
    }


_LIST = text(
    """
    SELECT id, media_type, storage_key, external_url, alt_text, position, is_primary
    FROM catalog_product_media
    WHERE product_id = :pid AND archived_at IS NULL
    ORDER BY is_primary DESC, position, created_at
    """
)
_PRODUCT_EXISTS = text("SELECT 1 FROM catalog_products WHERE id = :pid AND archived_at IS NULL")


async def _guard_product(db: AsyncSession, product_id: UUID) -> None:
    if (await db.execute(_PRODUCT_EXISTS, {"pid": str(product_id)})).first() is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")


@router.get("")
async def list_media(
    product_id: UUID,
    context: Annotated[TenantContext, Depends(require_permission("catalog.product.read"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[dict]:
    await _guard_product(db, product_id)
    rows = (await db.execute(_LIST, {"pid": str(product_id)})).all()
    return [_serialize(r) for r in rows]


@router.post("", status_code=201)
async def upload_media(
    product_id: UUID,
    context: Annotated[TenantContext, Depends(require_permission("catalog.product.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
    file: Annotated[UploadFile, File()],
    alt_text: Annotated[str | None, Form()] = None,
) -> dict:
    await _guard_product(db, product_id)
    ext = _EXT_BY_TYPE.get(file.content_type or "")
    if ext is None:
        raise HTTPException(status_code=415, detail="Formato no soportado (usa JPG, PNG, WEBP, AVIF o GIF)")
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (máx 25 MB)")
    if not data:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    media_id = uuid.uuid4()
    key = f"products/{product_id}/{media_id}.{ext}"
    dest = _media_root() / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    stats = (
        await db.execute(
            text(
                "SELECT COALESCE(MAX(position), -1) + 1 AS next_pos, COUNT(*) AS cnt "
                "FROM catalog_product_media WHERE product_id = :pid AND archived_at IS NULL"
            ),
            {"pid": str(product_id)},
        )
    ).first()
    is_primary = stats.cnt == 0  # first photo of the product becomes the cover

    await db.execute(
        text(
            """
            INSERT INTO catalog_product_media
              (id, tenant_id, product_id, media_type, storage_key, original_name, content_type, byte_size, alt_text, position, is_primary)
            VALUES
              (:id, :tenant, :pid, 'image', :key, :orig, :ct, :size, :alt, :pos, :primary)
            """
        ),
        {
            "id": str(media_id),
            "tenant": str(context.tenant_id),
            "pid": str(product_id),
            "key": key,
            "orig": file.filename,
            "ct": file.content_type,
            "size": len(data),
            "alt": alt_text,
            "pos": stats.next_pos,
            "primary": is_primary,
        },
    )
    await db.commit()
    return {
        "id": str(media_id),
        "media_type": "image",
        "url": f"/media/{key}",
        "alt_text": alt_text,
        "position": stats.next_pos,
        "is_primary": is_primary,
    }


class VideoEmbed(BaseModel):
    external_url: str
    alt_text: str | None = None


@router.post("/video", status_code=201)
async def add_video(
    product_id: UUID,
    payload: VideoEmbed,
    context: Annotated[TenantContext, Depends(require_permission("catalog.product.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    await _guard_product(db, product_id)
    url = payload.external_url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL de video inválida")
    media_id = uuid.uuid4()
    next_pos = (
        await db.execute(
            text("SELECT COALESCE(MAX(position), -1) + 1 AS p FROM catalog_product_media WHERE product_id = :pid AND archived_at IS NULL"),
            {"pid": str(product_id)},
        )
    ).scalar_one()
    await db.execute(
        text(
            "INSERT INTO catalog_product_media (id, tenant_id, product_id, media_type, external_url, alt_text, position, is_primary) "
            "VALUES (:id, :tenant, :pid, 'video', :url, :alt, :pos, false)"
        ),
        {"id": str(media_id), "tenant": str(context.tenant_id), "pid": str(product_id), "url": url, "alt": payload.alt_text, "pos": next_pos},
    )
    await db.commit()
    return {"id": str(media_id), "media_type": "video", "url": url, "alt_text": payload.alt_text, "position": next_pos, "is_primary": False}


@router.delete("/{media_id}", status_code=204)
async def delete_media(
    product_id: UUID,
    media_id: UUID,
    context: Annotated[TenantContext, Depends(require_permission("catalog.product.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    row = (
        await db.execute(
            text("SELECT storage_key, is_primary FROM catalog_product_media WHERE id = :id AND product_id = :pid"),
            {"id": str(media_id), "pid": str(product_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Medio no encontrado")
    await db.execute(text("DELETE FROM catalog_product_media WHERE id = :id"), {"id": str(media_id)})
    # If the cover was removed, promote the next remaining medium.
    if row.is_primary:
        nxt = (
            await db.execute(
                text("SELECT id FROM catalog_product_media WHERE product_id = :pid AND archived_at IS NULL ORDER BY position, created_at LIMIT 1"),
                {"pid": str(product_id)},
            )
        ).first()
        if nxt is not None:
            await db.execute(text("UPDATE catalog_product_media SET is_primary = true WHERE id = :id"), {"id": str(nxt.id)})
    await db.commit()
    if row.storage_key:
        (_media_root() / row.storage_key).unlink(missing_ok=True)


@router.post("/{media_id}/primary")
async def set_primary(
    product_id: UUID,
    media_id: UUID,
    context: Annotated[TenantContext, Depends(require_permission("catalog.product.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    hit = (
        await db.execute(
            text("SELECT 1 FROM catalog_product_media WHERE id = :id AND product_id = :pid"),
            {"id": str(media_id), "pid": str(product_id)},
        )
    ).first()
    if hit is None:
        raise HTTPException(status_code=404, detail="Medio no encontrado")
    await db.execute(text("UPDATE catalog_product_media SET is_primary = false WHERE product_id = :pid"), {"pid": str(product_id)})
    await db.execute(text("UPDATE catalog_product_media SET is_primary = true WHERE id = :id"), {"id": str(media_id)})
    await db.commit()
    return {"id": str(media_id), "is_primary": True}


class ReorderPayload(BaseModel):
    ids: list[UUID]


@router.post("/reorder")
async def reorder_media(
    product_id: UUID,
    payload: ReorderPayload,
    context: Annotated[TenantContext, Depends(require_permission("catalog.product.update"))],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    for position, media_id in enumerate(payload.ids):
        await db.execute(
            text("UPDATE catalog_product_media SET position = :pos WHERE id = :id AND product_id = :pid"),
            {"pos": position, "id": str(media_id), "pid": str(product_id)},
        )
    await db.commit()
    return {"ok": True, "count": len(payload.ids)}
