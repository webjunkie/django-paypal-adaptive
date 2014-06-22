Django Paypal Adaptive
======================

[![Build Status](https://travis-ci.org/FundedByMe/django-paypal-adaptive.png?branch=master)](https://travis-ci.org/FundedByMe/django-paypal-adaptive)
[![Downloads](https://pypip.in/v/django-paypal-adaptive/badge.png)](https://pypi.python.org/pypi/django-paypal-adaptive)

The API and the modules in this repository might be subject to smaller
changes and not all Paypal Adaptive endpoints are covered. FundedByMe
will help make the covering of the Pay, Preapproval and IPN endpoints as good
as possible but we might not have the resources to perfect this project.

Making Preapprovals and using them to create Payments is fully supported
together with Paypal's IPN push API. Please reach out to us if you're
interested in helping maintaining this package.

Installation
============

Install package from PyPI:

    $ pip install django-paypal-adaptive

Add to your project's `INSTALLED_APPS` setting:

```python
INSTALLED_APPS = (
    # …
    'paypaladaptive',
)
```

Add to your url config:

```python
url(r'^paypaladaptive/', include('paypaladaptive.urls'))
```

Sync the database:

    $ python manage.py syncdb

Or if you're using __South__ you might want to add an initial migration for future changes:

    $ python manage.py schemamigration paypaladaptive --initial
    $ python manage.py syncdb --migrate


Usage
=====

Examples
--------
Test the calls with sandbox account emails or you'll probably get 'Account is restricted' errors.

Simple payment:
https://developer.paypal.com/webapps/developer/docs/classic/adaptive-payments/integration-guide/APIntro/#id0937N0Q0JY4

```python
from paypaladaptive.models import Payment
from moneyed import Money, USD
from paypaladaptive.api import ReceiverList, Receiver

receiver = Receiver(amount=100, email="receiver1@example.com")
receivers = ReceiverList([receiver])

payment = Payment()
payment.money = Money(receivers.total_amount, USD)
payment.save()
payment.process(receivers)

# Redirect the user to the next_url() value
redirect_url = payment.next_url()
```

Parallel payment with 2 receivers:

```python
from paypaladaptive.models import Payment
from moneyed import Money, USD
from paypaladaptive.api import ReceiverList, Receiver

receiver1 = Receiver(amount=100, email="receiver1@example.com")
receiver2 = Receiver(amount=1900, email="receiver2@example.com")
receivers = ReceiverList([receiver1, receiver2])

payment = Payment()
payment.money = Money(receivers.total_amount, USD)
payment.save()
payment.process(receivers)

# Redirect the user to the next_url() value
redirect_url = payment.next_url()
```

Parallel payment with 2 receivers where the sender pays the fees and we also set reverseAllParallelPaymentsOnError to True:
https://developer.paypal.com/webapps/developer/docs/classic/adaptive-payments/integration-guide/APIntro/#id091QF0
Learn more about PAY API operation fields: https://developer.paypal.com/webapps/developer/docs/classic/api/adaptive-payments/Pay_API_Operation/

```python
from paypaladaptive.models import Payment
from moneyed import Money, USD
from paypaladaptive.api import ReceiverList, Receiver

receiver1 = Receiver(amount=100, email="receiver1@example.com")
receiver2 = Receiver(amount=1900, email="receiver2@example.com")
receivers = ReceiverList([receiver1, receiver2])

payment = Payment()
payment.money = Money(receivers.total_amount, USD)
payment.save()
payment.process(
    receivers,
    reverseAllParallelPaymentsOnError=True,
    feesPayer='SENDER',
    )

# Redirect the user to the next_url() value
redirect_url = payment.next_url()

response = payment.update(save=False)
payment.debug_response['feesPayer'] # SENDER
payment.debug_response['reverseAllParallelPaymentsOnError'] # true
```

Chained payment with 2 receivers:
https://developer.paypal.com/webapps/developer/docs/classic/adaptive-payments/integration-guide/APIntro/#id091QF0I30YK
Primary gets: $2
Secodaries get: $4

```python
from paypaladaptive.models import Payment
from moneyed import Money, USD
from paypaladaptive.api import ReceiverList, Receiver

primary = Receiver(amount=10, email="primary@example.com", primary=True)
secondary1 = Receiver(amount=4, email="secondary1@example.com")
secondary2 = Receiver(amount=4, email="secondary2@example.com")
receivers = ReceiverList([primary, secondary1, secondary2])

payment = Payment()
payment.money = Money(primary.amount, USD)
payment.save()
payment.process(receivers)

# Redirect the user to the next_url() value
redirect_url = payment.next_url()
```

Create and process a preapproval for a payment.

```python
from paypaladaptive.models import Preapproval
from moneyed import Money, USD

preapproval = Preapproval()
preapproval.money = Money(2000, USD)
preapproval.save()
preapproval.process(next='/home/', displayMaxTotalAmount=True)

# Redirect the user to the next_url() value
redirect_url = preapproval.next_url()
```

Create and process a payment to two receivers from a preapproval key.

```python
from paypaladaptive.models import Payment
from paypaladaptive.api import ReceiverList, Receiver
from moneyed import Money, USD

key = 'PA-2MT146200X905683P'
platform = Receiver(amount=100, email="merchant@example.com", primary=False)
merchant = Receiver(amount=1900, email="mrbuyer@antonagestam.se", primary=True)
receivers = ReceiverList([platform, merchant])

p = Payment()
p.money=Money(2000, USD)
p.save()
p.process(receivers, preapproval_key=key)
```

Convert currencies:
In this case no models are involved, we just call the ConvertCurrency API endpoint.
https://developer.paypal.com/webapps/developer/docs/classic/api/adaptive-payments/ConvertCurrency_API_Operation/

```python
from paypaladaptive.api import ConvertCurrency, MoneyList
from moneyed import Money, USD, GBP

convert_from = MoneyList([Money(10.55, USD), Money(20.64, GBP)])
convert_to = ['CAD', 'AUD', 'HUF']
response = ConvertCurrency(convert_from, convert_to).call()
```

specifiying conversionType and countryCode fields:
PayPal country codes: https://developer.paypal.com/webapps/developer/docs/classic/api/country_codes/

```python
convert_from = MoneyList([Money(10.55, USD), Money(20.64, GBP)])
convert_to = ['CAD', 'AUD', 'HUF']
response = ConvertCurrency(convert_from, convert_to, conversionType='BALANCE_TRANSFER', countryCode='HUF').call()
```



IPN vs Delayed Updates
----------------------

Paypal Adaptive uses IPN messages to ping your server about Payment and
Preapproval updates. Using IPN requires you to listen for incoming calls from
Paypal. Sometimes Paypal has issues with their IPN service and therefor you
might sometimes need to ping them for an update of the status instead. This
package comes with both and they can be used in parallel. That way you get both
the speed and asynchronous nature of IPN messages and the stability of delayed
lookups. Delayed lookups are disabled by default and requires Celery to be
installed. To install this requirement automatically, use:

    $ pip install django-paypal-adaptive[delayed-updates]

And set `PAYPAL_USE_DELAYED_UPDATES` to `True` in your Django settings. Note
that this requires you to setup Celery on your own.

You can also implement your own background tasks and logic and call
`Preapproval.update()` and `Payment.update()` when you find it appropriate.

Models
======

The Payment and Preapproval inherit from an abstract model PaypalAdaptive and
therefor shares some data fields.

__`PaypalAdaptive.money`__

`money` is a django-money MoneyField. MoneyField extends Django's DecimalField
so has max_digits and decimal_places attributes that can be set with the
`PAYPAL_MAX_DIGITS` and `PAYPAL_DECIMAL_PLACES` settings.

__`PaypalAdaptive.created_date`__

DateTimeField with `auto_now_add=True`.

__`PaypalAdaptive.debug_request`__

Raw request body (JSON)

__`PaypalAdaptive.debug_response`__

Raw response body (JSON)

__`PaypalAdaptive.secret_uuid`__

Secret identifier of each object.

Payment
-------

__`Payment.status`__

Possible values are:

    'new'  # Payment only exists locally
    'created'  # Payment exists on Paypal
    'error'  # Something along the process has gone wrong. Check status_detail
             # for more info.
    'returned'  # User has returned via the Payment return_url
    'completed'  # The Payment is complete
    'refunded'  # The Payment is refunded
    'canceled'  # The Payment has been canceled

__`Payment.status_detail`__

Stores error messages from the latest transaction

__`Payment.pay_key`__

Corresponds to Paypal Adaptive's `payKey`

__`Payment.transaction_id`__

Corresponds to Paypal Adaptive's `transactionId`

Preapproval
-----------

__`Preapproval.status`__

Possible values are:

    'new'  # Preapproval only exists locally — not known to Paypal
    'created'  # Preapproval has been saved on Paypal
    'error'  # Something has gone wrong, check status_detail for more info
    'returned'  # User has returned via the Preapproval return_url
    'approved'  # Preapproval is completed — ready to be used in payment
    'canceled'  # Preapproval has been canceled
    'used'  # Preapproval has been used in payment

__`Preapproval.status_detail`__

Stores error messages from the latest transaction

__`Preapproval.valid_until_date`__

Preapproval expiry date

Settings
========

**`django.conf.settings.PAYPAL_APPLICATION_ID`**

Your Paypal application ID. Will default to `APP-80W284485P519543T` if
`DEBUG` is set to `True`.

**`django.conf.settings.PAYPAL_USERID`**

Paypal User ID

**`django.conf.settings.PAYPAL_PASSWORD`**

Paypal password

**`django.conf.settings.PAYPAL_SIGNATURE`**

Paypal signature

**`django.conf.settings.PAYPAL_EMAIL`**

Paypal Email

**`django.conf.settings.PAYPAL_USE_IPN`**

Whether or not to listen for incoming IPN messages. Defaults to `True`.

**`django.conf.settings.PAYPAL_IPN_HTTP_PROTOCOL`**

'http' or 'https'. Defaults to settings.DEFAULT_HTTP_PROTOCOL. If settings.DEFAULT_HTTP_PROTOCOL is not set it defaults to 'http'.

**`django.conf.settings.PAYPAL_IPN_DOMAIN`**

Default is None in which case Site.objects.get_current().domain is used.
Useful if you want to test the IPN in localhost (e.g. https://ngrok.com/).

**`django.conf.settings.PAYPAL_USE_DELAYED_UPDATES`**

Whether or not to schedule update tasks for Preapprovals and Payments. Defaults
to `False`.

**`django.conf.settings.DEFAULT_CURRENCY`**

Used by python-money, will default to USD

**`django.conf.settings.PAYPAL_DECIMAL_PLACES`**

Number of decimal places assigned to the MoneyField (used by Payment and
Preapproval models).

**`django.conf.settings.PAYPAL_MAX_DIGITS`**

Max number of digits assigned to the Moneyfield (used by Payment and Preapproval
models).

**`django.conf.settings.PAYPAL_TEST_WITH_MOCK`**

Set whether tests should be run with built-in mocking responses and requests
or if the testing should spawn requests that hits Paypal's APIs directly.
Defaults to True.

Run tests
=========

To run the tests, first install the test requirements:

    $ [sudo] pip install -r requirements_test.txt --use-mirrors

The script that runs the tests simulates an installed Django app and is located
in `runtests.py`. Execute it like this:

    $ python runtests.py

Contributing
============

Do you want to contribute? We'll gladly accept pull requests as long as your code
is well tested and contributes to the goal of this library.

License
=======

<a rel="license" href="http://creativecommons.org/licenses/by/3.0/deed.sv"><img alt="Creative Commons-licens" style="border-width:0" src="http://i.creativecommons.org/l/by/3.0/80x15.png" /></a><br /><span xmlns:dct="http://purl.org/dc/terms/" property="dct:title">django-paypal-adaptive</span> av <a xmlns:cc="http://creativecommons.org/ns#" href="https://github.com/FundedByMe/django-paypal-adaptive" property="cc:attributionName" rel="cc:attributionURL">FundedByMe</a> är licensierad under en <a rel="license" href="http://creativecommons.org/licenses/by/3.0/deed.sv">Creative Commons Erkännande 3.0 Unported licens</a>.<br />Based on a work at <a xmlns:dct="http://purl.org/dc/terms/" href="https://github.com/gmcguire/django-paypal-adaptive" rel="dct:source">https://github.com/gmcguire/django-paypal-adaptive</a>.
