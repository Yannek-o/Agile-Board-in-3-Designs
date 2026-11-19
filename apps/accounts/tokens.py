"""Invitation tokens for new employee accounts.

Same construction as Django's password reset tokens (bound to the password
hash and last login, so a token is void once the password has been set), but
with a separate salt and a longer validity period.
"""

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.crypto import constant_time_compare
from django.utils.http import base36_to_int


class InvitationTokenGenerator(PasswordResetTokenGenerator):
    key_salt = "apps.accounts.tokens.InvitationTokenGenerator"

    def check_token(self, user, token) -> bool:
        if not (user and token):
            return False
        try:
            timestamp_b36, _ = token.split("-")
            timestamp = base36_to_int(timestamp_b36)
        except ValueError:
            return False
        for secret in [self.secret, *self.secret_fallbacks]:
            expected = self._make_token_with_timestamp(user, timestamp, secret)
            if constant_time_compare(expected, token):
                break
        else:
            return False
        age = self._num_seconds(self._now()) - timestamp
        return age <= settings.INVITATION_TIMEOUT


invitation_token_generator = InvitationTokenGenerator()
