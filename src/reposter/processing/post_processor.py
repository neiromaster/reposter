from collections.abc import Sequence

from ..models.dto import Post as VkPost
from ..models.dto import TelegramPost
from .steps import ProcessingStep


class PostProcessor:
    def __init__(self, steps: Sequence[ProcessingStep]) -> None:
        self.steps = steps

    async def process_post(self, post: VkPost) -> TelegramPost:
        prepared_post = TelegramPost(text=post.text, attachments=[])

        for step in self.steps:
            await step.process(post, prepared_post)

        return prepared_post
