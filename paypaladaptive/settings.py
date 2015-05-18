from datetime import timedelta
from django.conf import settings


DEBUG = getattr(settings, "DEBUG", False)


PAYPAL_ENDPOINT = getattr(settings, 'PAYPAL_ENDPOINT', 'https://svcs.sandbox.paypal.com/AdaptivePayments/' if DEBUG else 'https://svcs.paypal.com/AdaptivePayments/')
PAYPAL_ENDPOINT_ACCOUNTS = getattr(settings, 'PAYPAL_ENDPOINT_ACCOUNTS', 'https://svcs.sandbox.paypal.com/AdaptiveAccounts/' if DEBUG else 'https://svcs.paypal.com/AdaptiveAccounts/')
PAYPAL_PAYMENT_HOST = getattr(settings, 'PAYPAL_PAYMENT_HOST', 'https://www.sandbox.paypal.com/au/cgi-bin/webscr' if DEBUG else 'https://www.paypal.com/webscr')
PAYPAL_EMBEDDED_ENDPOINT = getattr(settings, 'PAYPAL_EMBEDDED_ENDPOINT', 'https://www.sandbox.paypal.com/webapps/adaptivepayment/flow/pay' if DEBUG else 'https://paypal.com/webapps/adaptivepayment/flow/pay')
PAYPAL_APPLICATION_ID = getattr(settings, 'PAYPAL_APPLICATION_ID', 'APP-80W284485P519543T')

# These settings are required
PAYPAL_USERID = settings.PAYPAL_USERID
PAYPAL_PASSWORD = settings.PAYPAL_PASSWORD
PAYPAL_SIGNATURE = settings.PAYPAL_SIGNATURE
PAYPAL_EMAIL = settings.PAYPAL_EMAIL

USE_IPN = getattr(settings, 'PAYPAL_USE_IPN', True)
IPN_DOMAIN = getattr(settings, 'PAYPAL_IPN_DOMAIN', None)
IPN_HTTP_PROTOCOL = getattr(
    settings,
    'PAYPAL_IPN_HTTP_PROTOCOL',
    getattr(settings, 'DEFAULT_HTTP_PROTOCOL', 'http')
    )
IPN_LOG_ENABLED = getattr(settings, 'PAYPAL_IPN_LOG_ENABLED', False)
USE_DELAYED_UPDATES = getattr(settings, 'PAYPAL_USE_DELAYED_UPDATES', False)
DELAYED_UPDATE_COUNTDOWN = getattr(
    settings, 'PAYPAL_DELAYED_UPDATE_COUNTDOWN', timedelta(minutes=60))
USE_EMBEDDED = getattr(settings, 'PAYPAL_USE_EMBEDDED', True)
SHIPPING = getattr(settings, 'PAYPAL_USE_SHIPPING', False)

DEFAULT_CURRENCY = getattr(settings, 'DEFAULT_CURRENCY', 'USD')

DECIMAL_PLACES = getattr(settings, 'PAYPAL_DECIMAL_PLACES', 2)
MAX_DIGITS = getattr(settings, 'PAYPAL_MAX_DIGITS', 10)

# Should tests hit Paypaladaptive or not? Defaults to using mock responses
TEST_WITH_MOCK = getattr(settings, 'PAYPAL_TEST_WITH_MOCK', True)
