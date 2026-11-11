import logging
import re


class InvitationTokenFilter(logging.Filter):
    pattern = re.compile(r"(/accounts/invitations/accept/)[^/?\s\"']+/")
    password_reset_pattern = re.compile(
        r"(/accounts/password/reset/key/)[0-9A-Za-z]+-[^/?\s\"']+/"
    )

    def filter(self, record):
        record.msg = self.pattern.sub(r"\1[oculto]/", record.getMessage())
        record.msg = self.password_reset_pattern.sub(r"\1[oculto]/", record.msg)
        record.args = ()
        return True
