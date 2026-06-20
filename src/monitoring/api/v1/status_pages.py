from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status

from monitoring.dependencies import CurrentUser, DbSession
from monitoring.schemas.status_page import (
    PublicStatusPageResponse,
    StatusPageCreate,
    StatusPageList,
    StatusPageResponse,
    StatusPageServiceCreate,
    StatusPageServiceList,
    StatusPageServiceResponse,
    StatusPageUpdate,
)
from monitoring.services.organization_service import OrganizationService
from monitoring.services.status_page_service import StatusPageService

router = APIRouter()
public_router = APIRouter()


async def _ensure_page_access(
    db: DbSession,
    status_page_id: uuid.UUID,
    current_user: CurrentUser | None,
):
    status_page = await StatusPageService(db).get_status_page(status_page_id)
    if status_page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Status page {status_page_id} not found",
        )
    if current_user is None or not await OrganizationService(db).user_can_access(
        current_user,
        status_page.organization_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Status page {status_page_id} not found",
        )
    return status_page


@router.post("/", response_model=StatusPageResponse, status_code=status.HTTP_201_CREATED)
async def create_status_page(
    data: StatusPageCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> StatusPageResponse:
    organization = await OrganizationService(db).get_organization(data.organization_id)
    if organization is None or not await OrganizationService(db).user_can_access(
        current_user,
        organization.id,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {data.organization_id} not found",
        )
    try:
        status_page = await StatusPageService(db).create_status_page(data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return StatusPageResponse.model_validate(status_page)


@router.get("/", response_model=StatusPageList)
async def list_status_pages(
    db: DbSession,
    current_user: CurrentUser,
    organization_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> StatusPageList:
    organization = await OrganizationService(db).get_organization(organization_id)
    if organization is None or not await OrganizationService(db).user_can_access(
        current_user,
        organization.id,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {organization_id} not found",
        )
    pages, total = await StatusPageService(db).list_status_pages(
        organization.id,
        skip=skip,
        limit=limit,
    )
    return StatusPageList(
        status_pages=[StatusPageResponse.model_validate(page) for page in pages],
        total=total,
    )


@router.get("/{status_page_id}", response_model=StatusPageResponse)
async def get_status_page(
    status_page_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> StatusPageResponse:
    status_page = await _ensure_page_access(db, status_page_id, current_user)
    return StatusPageResponse.model_validate(status_page)


@router.patch("/{status_page_id}", response_model=StatusPageResponse)
async def update_status_page(
    status_page_id: uuid.UUID,
    data: StatusPageUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> StatusPageResponse:
    await _ensure_page_access(db, status_page_id, current_user)
    try:
        status_page = await StatusPageService(db).update_status_page(status_page_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if status_page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return StatusPageResponse.model_validate(status_page)


@router.delete("/{status_page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_status_page(
    status_page_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> Response:
    await _ensure_page_access(db, status_page_id, current_user)
    await StatusPageService(db).delete_status_page(status_page_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{status_page_id}/services",
    response_model=StatusPageServiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_status_page_service(
    status_page_id: uuid.UUID,
    data: StatusPageServiceCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> StatusPageServiceResponse:
    await _ensure_page_access(db, status_page_id, current_user)
    try:
        service = await StatusPageService(db).add_service(status_page_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return StatusPageServiceResponse.model_validate(service)


@router.get("/{status_page_id}/services", response_model=StatusPageServiceList)
async def list_status_page_services(
    status_page_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> StatusPageServiceList:
    await _ensure_page_access(db, status_page_id, current_user)
    result = await StatusPageService(db).list_services(status_page_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    services, total = result
    return StatusPageServiceList(
        services=[StatusPageServiceResponse.model_validate(service) for service in services],
        total=total,
    )


@router.delete(
    "/{status_page_id}/services/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_status_page_service(
    status_page_id: uuid.UUID,
    service_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> Response:
    await _ensure_page_access(db, status_page_id, current_user)
    deleted = await StatusPageService(db).delete_service(status_page_id, service_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public_router.get("/{slug}", response_model=PublicStatusPageResponse)
async def get_public_status_page(
    slug: str,
    db: DbSession,
) -> PublicStatusPageResponse:
    payload = await StatusPageService(db).get_public_status_page(slug)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Status page {slug} not found",
        )
    return PublicStatusPageResponse.model_validate(payload)
