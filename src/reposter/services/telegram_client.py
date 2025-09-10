import asyncio


class TelegramClient:
    def __init__(self, token: str):
        self._token = token

    async def send_message(self, chat_id: int, text: str):
        print(f"Sending to Telegram chat {chat_id}: {text}")
        # Add actual implementation here
        await asyncio.sleep(0.1)
