import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from monitoring.services.telegram_service import register_webhook


async def main() -> None:
    print("Registering Telegram webhook...")
    await register_webhook()
    print("Webhook registration attempt complete.")


if __name__ == "__main__":
    asyncio.run(main())
