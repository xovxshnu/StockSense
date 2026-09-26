"""Password-reset delivery.

No email provider exists yet. In development the reset token is written to the
server log so the flow can be exercised end to end; in any other environment
nothing is delivered. Replace `deliver_password_reset` with a real email sender
for production.
"""

import logging

from app.core.config import Settings

logger = logging.getLogger(__name__)


def deliver_password_reset(settings: Settings, email: str, token: str) -> None:
    if settings.environment == "development":
        logger.warning("DEV ONLY: password reset token for %s: %s", email, token)
