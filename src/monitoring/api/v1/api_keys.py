from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from monitoring.dependencies import CurrentUser, DbSession
from monitoring.schemas.api_key import (
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    ApiKeyList,
    ApiKeyResponse,
)
from monitoring.services.api_key_service import ApiKeyService
from monitoring.services.organization_service import OrganizationService

router = APIRouter()



def _key_response(api_key) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=api_key.public_id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        permissions=api_key.permissions,
        last_used_at=api_key.last_used_at,
        expires_at=api_key.expires_at,
        revoked_at=api_key.revoked_at,
        created_at=api_key.created_at,
    )


async def _resolve_org(
    organization_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> int:
    organization = await OrganizationService(db).get_organization(organization_id)
    if organization is None or not await OrganizationService(db).user_can_access(
        current_user,
        organization.id,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {organization_id} not found",
        )
    return organization.id


@router.post(
    "/",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    data: ApiKeyCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> ApiKeyCreatedResponse:
    """Create an API key. The raw key is returned exactly once."""
    organization_id = await _resolve_org(data.organization_id, db, current_user)
    try:
        api_key, raw_key = await ApiKeyService(db).create_key(organization_id, data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    await db.commit()
    response = ApiKeyCreatedResponse(
        id=api_key.public_id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        permissions=api_key.permissions,
        last_used_at=api_key.last_used_at,
        expires_at=api_key.expires_at,
        revoked_at=api_key.revoked_at,
        created_at=api_key.created_at,
        key=raw_key,
    )
    return response


@router.get("/", response_model=ApiKeyList)
async def list_api_keys(
    db: DbSession,
    current_user: CurrentUser,
    organization_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> ApiKeyList:
    """List API keys for an organization (never includes raw keys)."""
    organization_id_internal = await _resolve_org(organization_id, db, current_user)
    keys, total = await ApiKeyService(db).list_keys(
        organization_id_internal,
        skip=skip,
        limit=limit,
    )
    return ApiKeyList(
        api_keys=[_key_response(key) for key in keys],
        total=total,
    )


@router.delete("/{api_key_id}", response_model=ApiKeyResponse)
async def revoke_api_key(
    api_key_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> ApiKeyResponse:
    """Revoke an API key."""
    api_key = await ApiKeyService(db).get_key(api_key_id)
    if api_key is None or not await OrganizationService(db).user_can_access(
        current_user,
        api_key.organization_id,
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    revoked = await ApiKeyService(db).revoke_key(api_key_id)
    assert revoked is not None
    await db.commit()
    return _key_response(revoked)
