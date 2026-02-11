from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring.database import get_db

# Type alias for database dependency
DbSession = Annotated[AsyncSession, Depends(get_db)]
