from collections.abc import Sequence

from ..exceptions import SkipPostException
from ..models import Post as VkPost
from ..models import PreparedPost
from .steps import ProcessingStep


class PostProcessor:
    def __init__(self, steps: Sequence[ProcessingStep]) -> None:
        self.steps = steps

    async def process_post(self, post: VkPost) -> PreparedPost | None:
        prepared_post = PreparedPost(text=post.text, attachments=[])

        try:
            for step in self.steps:
                await step.process(post, prepared_post)
        except SkipPostException:
            return None

        return prepared_post
