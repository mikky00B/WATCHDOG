from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.models.client import Client
from monitoring.schemas.client import ClientCreate, ClientUpdate


class ClientService:
    """Business logic for organization client groupings."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_client(self, organization_id: int, data: ClientCreate) -> Client:
        client = Client(
            organization_id=organization_id,
            name=data.name,
            contact_email=str(data.contact_email) if data.contact_email is not None else None,
            logo_url=str(data.logo_url) if data.logo_url is not None else None,
            notes=data.notes,
        )
        self.db.add(client)
        await self.db.flush()
        await self.db.refresh(client)
        return client

    async def get_client(self, client_id: uuid.UUID) -> Client | None:
        result = await self.db.execute(select(Client).where(Client.public_id == client_id))
        return result.scalar_one_or_none()

    async def list_clients(
        self,
        organization_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[Client], int]:
        base_stmt = select(Client).where(Client.organization_id == organization_id)
        total = (
            await self.db.execute(select(func.count()).select_from(base_stmt.subquery()))
        ).scalar() or 0
        result = await self.db.execute(
            base_stmt.order_by(Client.name.asc()).offset(skip).limit(limit),
        )
        return list(result.scalars().all()), total

    async def update_client(self, client_id: uuid.UUID, data: ClientUpdate) -> Client | None:
        client = await self.get_client(client_id)
        if client is None:
            return None

        for key, value in data.model_dump(exclude_unset=True).items():
            if key in {"contact_email", "logo_url"} and value is not None:
                value = str(value)
            setattr(client, key, value)

        await self.db.flush()
        await self.db.refresh(client)
        return client

    async def delete_client(self, client_id: uuid.UUID) -> bool:
        client = await self.get_client(client_id)
        if client is None:
            return False

        await self.db.delete(client)
        return True
