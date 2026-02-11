# Contributing to Monitoring Platform

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on what's best for the project
- Show empathy towards other contributors

## Development Setup

### Prerequisites

- Python 3.11 or higher
- PostgreSQL 12 or higher
- Git
- Poetry (recommended) or pip

### Initial Setup

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/monitoring-platform.git
   cd monitoring-platform
   ```

3. Install dependencies:
   ```bash
   poetry install
   # or
   pip install -r requirements.txt
   ```

4. Set up pre-commit hooks:
   ```bash
   poetry run pre-commit install
   ```

5. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Workflow

### 1. Make Changes

- Follow the coding standards (see below)
- Write tests for new features
- Update documentation as needed
- Add entries to DECISION_LOG.md for architectural changes

### 2. Run Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=src/monitoring --cov-report=html

# Run specific test
poetry run pytest tests/unit/test_services/test_monitor_service.py
```

### 3. Code Quality Checks

```bash
# Type checking
poetry run mypy src/

# Linting
poetry run ruff check src/

# Auto-fix issues
poetry run ruff check src/ --fix

# Check for unused imports
poetry run autoflake --check --remove-all-unused-imports src/
```

### 4. Commit Changes

```bash
git add .
git commit -m "feat: add new feature"
```

Commit message format:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Test additions or changes
- `refactor:` Code refactoring
- `style:` Code style changes
- `perf:` Performance improvements
- `chore:` Maintenance tasks

### 5. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub.

## Coding Standards

### Python Style

- Follow PEP 8
- Use type hints for all functions
- Maximum line length: 100 characters
- Use meaningful variable names
- Write docstrings for all public functions/classes

### Type Hints

```python
# ✅ Good
def create_monitor(name: str, url: str) -> Monitor:
    ...

# ❌ Bad
def create_monitor(name, url):
    ...
```

### SQLAlchemy Models

Use SQLAlchemy 2.0 syntax:

```python
# ✅ Good
class Monitor(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))

# ❌ Bad
class Monitor(Base):
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
```

### Pydantic Schemas

Use Pydantic v2 syntax:

```python
# ✅ Good
class MonitorCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str

# ❌ Bad
class MonitorCreate(BaseModel):
    class Config:
        orm_mode = True
    name: str
```

### Async/Await

- Always use async/await for I/O operations
- Never use blocking calls in async functions
- Use `httpx` for HTTP requests, not `requests`

```python
# ✅ Good
async def check_endpoint(url: str) -> int:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.status_code

# ❌ Bad
async def check_endpoint(url: str) -> int:
    response = requests.get(url)  # Blocking!
    return response.status_code
```

### Error Handling

- Use specific exceptions
- Include context in error messages
- Log errors with structured logging

```python
# ✅ Good
async def get_monitor(monitor_id: UUID) -> Monitor:
    monitor = await db.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitor {monitor_id} not found"
        )
    return monitor

# ❌ Bad
async def get_monitor(monitor_id: UUID) -> Monitor:
    monitor = await db.get(Monitor, monitor_id)
    if not monitor:
        raise Exception("Not found")
    return monitor
```

### Logging

Use structured logging with context:

```python
# ✅ Good
logger.info(
    "monitor_created",
    monitor_id=monitor.id,
    monitor_name=monitor.name,
    url=monitor.url
)

# ❌ Bad
print(f"Created monitor {monitor.name}")
logger.info("Monitor created")
```

## Testing Guidelines

### Test Structure

- Unit tests in `tests/unit/`
- Integration tests in `tests/integration/`
- Use fixtures for common setup
- Mock external dependencies

### Writing Tests

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_monitor(test_db: AsyncSession) -> None:
    """Test creating a monitor."""
    service = MonitorService(test_db)
    
    data = MonitorCreate(
        name="Test Monitor",
        url="https://example.com",
        interval_seconds=60,
    )
    
    monitor = await service.create_monitor(data)
    
    assert monitor.id is not None
    assert monitor.name == "Test Monitor"
```

### Test Coverage

- Aim for >80% code coverage
- Test happy paths and error cases
- Test edge cases and boundary conditions

## Documentation

### Code Documentation

- Add docstrings to all public functions and classes
- Include parameter descriptions and return types
- Add usage examples for complex functions

```python
async def create_monitor(self, data: MonitorCreate) -> Monitor:
    """
    Create a new monitor.
    
    Args:
        data: Monitor creation data containing name, URL, and settings
        
    Returns:
        Created monitor instance with ID assigned
        
    Example:
        >>> service = MonitorService(db)
        >>> data = MonitorCreate(name="API", url="https://api.example.com")
        >>> monitor = await service.create_monitor(data)
    """
    monitor = Monitor(**data.model_dump())
    self.db.add(monitor)
    await self.db.flush()
    return monitor
```

### README Updates

- Update README.md for new features
- Add examples for new API endpoints
- Update configuration section for new settings

### Decision Log

For architectural changes, add entry to DECISION_LOG.md:

```markdown
## [2026-02-10 16:00] Decision: Add Caching Layer

**Context**: API responses are slow for frequently accessed data

**Options Considered**:
1. Redis cache with TTL
2. In-memory cache with LRU
3. PostgreSQL materialized views

**Decision**: We chose Option 1 (Redis cache)

**Reasoning**: 
- Distributed caching across instances
- Built-in TTL support
- Industry standard

**Risks/Trade-offs**:
- Additional infrastructure
- Cache invalidation complexity

**Documentation Reference**: https://redis.io/docs/
```

## Pull Request Guidelines

### Before Submitting

- [ ] All tests pass
- [ ] Code coverage >80%
- [ ] Linters pass (mypy, ruff)
- [ ] Documentation updated
- [ ] DECISION_LOG.md updated (if applicable)
- [ ] Pre-commit hooks pass

### PR Description

Include:
- Description of changes
- Motivation and context
- Screenshots (if UI changes)
- Breaking changes (if any)
- Related issues

### Review Process

- Maintainers will review within 3 days
- Address feedback promptly
- Keep discussions constructive
- CI must pass before merge

## Code Review Checklist

Reviewers should check:

- [ ] Code follows style guidelines
- [ ] Type hints are present
- [ ] Tests are comprehensive
- [ ] Error handling is appropriate
- [ ] Logging is structured
- [ ] Documentation is clear
- [ ] No security vulnerabilities
- [ ] Performance is acceptable

## Getting Help

- Open an issue for bugs or questions
- Check existing issues first
- Use discussions for general questions
- Tag maintainers if urgent

## Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Thanked in commit messages

Thank you for contributing! 🚀
