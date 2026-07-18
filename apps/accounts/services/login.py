"""Shared post-login processing for password and OAuth authentication."""

from __future__ import annotations

import logging

from django.contrib.auth.models import update_last_login
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services.points import apply_point_policy

logger = logging.getLogger("apps.accounts")


def complete_login(user: User, *, award_rewards: bool = True) -> None:
    """Apply the account and reward changes that every successful login needs.

    Password, Google, and Kakao login must use this function so dormant account
    recovery and login rewards cannot drift between authentication methods.
    Point policies are idempotent, so retries do not duplicate rewards.
    """

    update_last_login(None, user)
    was_dormant = user.status == "dormant"
    update_fields: list[str] = []

    if was_dormant:
        user.status = "active"
        update_fields.append("status")
    if user.dormancy_warning_sent_at is not None:
        user.dormancy_warning_sent_at = None
        update_fields.append("dormancy_warning_sent_at")
    if update_fields:
        update_fields.append("updated_at")
        user.save(update_fields=update_fields)

    if not award_rewards:
        return

    today = timezone.localdate().isoformat()
    try:
        apply_point_policy(
            user=user,
            reason_code="LOGIN.DAILY",
            reference_id=today,
            idempotency_key=f"LOGIN.DAILY:{user.id}:{today}",
            description="daily first login reward",
        )
    except ValueError:
        logger.info("daily login reward skipped user_id=%s", user.id)

    if was_dormant:
        try:
            apply_point_policy(
                user=user,
                reason_code="DORMANT.RETURN_LOGIN",
                reference_id=str(user.id),
                idempotency_key=f"DORMANT.RETURN_LOGIN:{user.id}",
                description="dormant account return reward",
            )
        except ValueError:
            logger.info("dormant return reward skipped user_id=%s", user.id)
