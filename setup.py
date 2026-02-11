"""Setup file for monitoring-platform package."""
from __future__ import annotations

from setuptools import find_packages, setup

setup(
    name="monitoring-platform",
    version="1.0.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.11",
    install_requires=[
        "fastapi==0.109.0",
        "uvicorn[standard]==0.27.0",
        "pydantic==2.5.3",
        "pydantic-settings==2.1.0",
        "sqlalchemy==2.0.25",
        "asyncpg==0.29.0",
        "alembic==1.13.1",
        "httpx==0.26.0",
        "structlog==24.1.0",
        "python-multipart==0.0.6",
    ],
)
