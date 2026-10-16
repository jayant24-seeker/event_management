"""Sending SMS. One function, so plugging in a real provider is a small change.

Development uses the "console" provider: the message goes to the server log, and the
login page shows the code so you can sign in without a phone.
"""
from flask import current_app


class SmsNotConfigured(RuntimeError):
    pass


def send_sms(phone, text):
    provider = current_app.config["SMS_PROVIDER"]
    if provider == "console":
        current_app.logger.info("SMS to %s: %s", phone, text)
        return True
    # MSG91 / Twilio / AWS SNS: add the API call here, with the key read from an environment variable.
    raise SmsNotConfigured(f"SMS provider {provider!r} is not set up")
