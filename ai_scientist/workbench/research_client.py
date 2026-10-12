"""Adapt upstream chat calls to the configured Workbench research actor."""
import time
from types import SimpleNamespace

class CodexResearchClient:
    """The small chat client surface used by upstream llm.get_response_from_llm."""
    workbench_research = True
    def __init__(self, owner):
        self.owner = owner
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, *, messages, **kwargs):
        from .research_images import detach_images
        messages, images = detach_images(messages, self.owner.root / 'research/image-input')
        response = self.owner.query(system_message={
            'Role': 'Fulfil the original research module request below using only verified experiment evidence.',
            'Messages': messages,
        }, user_message=None, image_paths=images)
        # Upstream make_llm_call's tracker expects these response attributes.
        # Actual token counts come from owner.call_agent, not fabricated usage.
        return SimpleNamespace(model=self.owner.service.config.codex_model, created=int(time.time()),
                               choices=[SimpleNamespace(message=SimpleNamespace(content=response))])


