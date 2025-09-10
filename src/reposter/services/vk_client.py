import asyncio


class VKClient:
    def __init__(self, api_key: str):
        self._api_key = api_key

    async def get_new_posts(self, group_id: int) -> list[str]:
        print(f"Fetching new posts from VK group {group_id}")
        # Add actual implementation here
        await asyncio.sleep(0.1)
        return []
