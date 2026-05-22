from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status

from monitoring.dependencies import CurrentUser, DbSession
from monitoring.schemas.client import ClientCreate, ClientList, ClientResponse, ClientUpdate
from monitoring.services.client_service import ClientService
from monitoring.services.organization_service import OrganizationService

router = APIRouter()


async def _get_authorized_organization(
    db: DbSession,
    organization_id: uuid.UUID,
    current_user: CurrentUser,
):
    organization_service = OrganizationService(db)
    organization = await organization_service.get_organization(organization_id)
    if organization is None or not await organization_service.user_can_access(
        current_user,
        organization.id,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {organization_id} not found",
        )
    return organization


async def _ensure_client_access(
    db: DbSession,
    organization_id: uuid.UUID,
    client_id: uuid.UUID,
    current_user: CurrentUser,
):
    organization = await _get_authorized_organization(db, organization_id, current_user)
    client = await ClientService(db).get_client(client_id)
    if client is None or client.organization_id != organization.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client {client_id} not found",
        )
    return client


@router.post(
    "/organizations/{organization_id}/clients",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_client(
    organization_id: uuid.UUID,
    data: ClientCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> ClientResponse:
    organization = await _get_authorized_organization(db, organization_id, current_user)
    client = await ClientService(db).create_client(organization.id, data)
    return ClientResponse.model_validate(client)


@router.get("/organizations/{organization_id}/clients", response_model=ClientList)
async def list_clients(
    organization_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> ClientList:
    organization = await _get_authorized_organization(db, organization_id, current_user)
    clients, total = await ClientService(db).list_clients(
        organization.id,
        skip=skip,
        limit=limit,
    )
    return ClientList(
        clients=[ClientResponse.model_validate(client) for client in clients],
        total=total,
    )


@router.get(
    "/organizations/{organization_id}/clients/{client_id}",
    response_model=ClientResponse,
)
async def get_client(
    organization_id: uuid.UUID,
    client_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> ClientResponse:
    client = await _ensure_client_access(db, organization_id, client_id, current_user)
    return ClientResponse.model_validate(client)


@router.patch(
    "/organizations/{organization_id}/clients/{client_id}",
    response_model=ClientResponse,
)
async def update_client(
    organization_id: uuid.UUID,
    client_id: uuid.UUID,
    data: ClientUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> ClientResponse:
    await _ensure_client_access(db, organization_id, client_id, current_user)
    client = await ClientService(db).update_client(client_id, data)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return ClientResponse.model_validate(client)


@router.delete(
    "/organizations/{organization_id}/clients/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_client(
    organization_id: uuid.UUID,
    client_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> Response:
    await _ensure_client_access(db, organization_id, client_id, current_user)
    await ClientService(db).delete_client(client_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
