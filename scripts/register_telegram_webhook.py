import asyncio

from monitoring.services.telegram_service import register_webhook


async def main():
    print("Registering Telegram webhook...")
    await register_webhook()
    print("Webhook registration attempt complete.")


if __name__ == "__main__":
    asyncio.run(main())
