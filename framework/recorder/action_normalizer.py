from __future__ import annotations

from framework.core.models import Action


class ActionNormalizer:
    """Placeholder for converting raw events to framework Action objects."""

    def normalize(self, raw_event: dict) -> Action:
        raise NotImplementedError("Action normalization is planned for the next phase.")
