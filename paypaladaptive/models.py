"""Models to support Paypal Adaptive API"""
import ast
import logging
from datetime import datetime, timedelta

from django.core.serializers.json import DjangoJSONEncoder
from django.core.urlresolvers import reverse
from django.db import models, transaction
from django.utils.translation import ugettext_lazy as _
from django.contrib.sites.models import Site
from django.utils import timezone
try:
    import json
except ImportError:
    import django.utils.simplejson as json

from djmoney.models.fields import MoneyField
from shortuuidfield import ShortUUIDField

from .helpers import get_http_protocol
from . import settings
from . import api


logger = logging.getLogger(__name__)


class PaypalAdaptive(models.Model):
    """Base fields used by all PaypalAdaptive models"""
    money = MoneyField(_(u'money'), max_digits=settings.MAX_DIGITS,
                       decimal_places=settings.DECIMAL_PLACES)
    created_date = models.DateTimeField(_(u'created on'), auto_now_add=True)
    secret_uuid = ShortUUIDField(verbose_name=_(u'secret UUID'))  # to verify return_url
    debug_request = models.TextField(_(u'raw request'), blank=True, null=True)
    debug_response = models.TextField(_(u'raw response'), blank=True,
                                      null=True)
    sender_email = models.EmailField(
        _(u'sender email'),
        blank=True,
        )

    class Meta:
        abstract = True

    def call(self, endpoint_class, *args, **kwargs):
        endpoint = endpoint_class(*args, **kwargs)

        try:
            res = endpoint.call()
        finally:
            self.debug_request = json.dumps(endpoint.data, cls=DjangoJSONEncoder)
            self.debug_response = endpoint.raw_response
            self.save()

        return res, endpoint

    def get_amount(self):
        return self.money.amount

    def set_amount(self, value):
        self.money.amount = value

    amount = property(get_amount, set_amount)

    def get_currency(self):
        return self.money.currency

    def set_currency(self, value):
        self.money.currency = value

    currency = property(get_currency, set_currency)

    @property
    def ipn_url(self):
        domain = settings.IPN_DOMAIN or Site.objects.get_current().domain
        kwargs = {'object_id': self.id,
                  'object_secret_uuid': self.secret_uuid}
        ipn_url = reverse('paypal-adaptive-ipn', kwargs=kwargs)
        return "%s://%s%s" % (settings.IPN_HTTP_PROTOCOL, domain, ipn_url)

    def get_update_kwargs(self):
        return {}

    def _parse_update_status_detail(self, response):
        return ''

    def _parse_update_sender_email(self, response):
        sender_email = ''
        sender = response.get('sender', None)
        if sender is not None:
            # in preapproval responses there are only an accountID key for sender
            sender_email = sender.get('email', '')
        return response.get('senderEmail', sender_email)

    def update(self, save=True, fields=None):
        if not hasattr(self, 'update_endpoint'):
            raise NotImplementedError(
                'Model need to specify an update endpoint')

        if fields is None:
            fields = ['status', 'status_detail', 'sender_email']

        try:
            __, endpoint = self.call(self.update_endpoint,
                                     **self.get_update_kwargs())
        except ValueError, e:
            model_name = self.__class__.__name__
            logger.warning('Could not update %s:\n%s', model_name, e.message)
        else:
            response = endpoint.response

            for field in fields:
                val = getattr(self, '_parse_update_%s' % field)(response)
                setattr(self, field, val)

            if save:
                self.save()

            return response

    @property
    def debug_request_dict(self):
        return json.loads(self.debug_request)

    @property
    def debug_response_dict(self):
        return json.loads(self.debug_response)


class Payment(PaypalAdaptive):
    """Models a payment made using Paypal"""

    update_endpoint = api.PaymentDetails

    STATUS_CHOICES = (
        ('new', _(u'New')),  # just saved locally
        ('created', _(u'Created')),  # payment created
        ('error', _(u'Error')),  # error occurred somewhere in the process
        ('canceled', _(u'Canceled')),  # the payment has been canceled
        ('returned', _(u'Returned')),  # user has returned via return_url
        ('completed', _(u'Completed')),  # the payment has been completed
        ('refunded', _(u'Refunded')),  # payment has been refunded
    )

    pay_key = models.CharField(_(u'paykey'), max_length=255)
    status = models.CharField(_(u'status'), max_length=10,
                              choices=STATUS_CHOICES, default='new')
    status_detail = models.TextField(_(u'detailed status'), blank=True)

    def save(self, *args, **kwargs):
        is_new = self.id is None

        super(Payment, self).save(*args, **kwargs)

        if settings.USE_DELAYED_UPDATES and is_new:
            from .tasks import update_payment
            update_payment.apply_async(
                args=[self.id],
                eta=datetime.now() + settings.DELAYED_UPDATE_COUNTDOWN)

    @property
    def return_url(self):
        current_site = Site.objects.get_current()
        kwargs = {'payment_id': self.id, 'secret_uuid': self.secret_uuid}
        return_url = reverse('paypal-adaptive-payment-return', kwargs=kwargs)
        return "%s://%s%s" % (get_http_protocol(), current_site, return_url)

    @property
    def cancel_url(self):
        current_site = Site.objects.get_current()
        kwargs = {'payment_id': self.id, 'secret_uuid': self.secret_uuid}
        cancel_url = reverse('paypal-adaptive-payment-cancel', kwargs=kwargs)
        return "%s://%s%s" % (get_http_protocol(), current_site, cancel_url)

    @transaction.atomic
    def process(self, receivers, preapproval=None, **kwargs):
        """Process the payment"""
        if self.status != 'new':
            raise ValueError(
                "This payment instance is already processed, "
                "it's status is not new."
                )

        endpoint_kwargs = {
            'money': self.money,
            'return_url': self.return_url,
            'cancel_url': self.cancel_url,
            }

        # Update return_url with ?next param
        if 'next' in kwargs:
            return_next = "%s?next=%s" % (self.return_url, kwargs.pop('next'))
            endpoint_kwargs.update({'return_url': return_next})

        # Update cancel_url
        if 'cancel' in kwargs:
            return_cancel = "%s?next=%s" % (self.cancel_url,
                                            kwargs.pop('cancel'))
            endpoint_kwargs.update({'cancel_url': return_cancel})

        # Set ipn_url
        if settings.USE_IPN:
            endpoint_kwargs.update({'ipn_url': self.ipn_url})

        # Append extra arguments
        endpoint_kwargs.update(**kwargs)

        # Validate type of receivers and check ReceiverList has primary,
        # otherwise assign first
        if not isinstance(receivers, api.ReceiverList):
            raise ValueError("receivers must be an instance of "
                             "ReceiverList")

        endpoint_kwargs.update({'receivers': receivers})

        # Use preapproval
        if preapproval is not None:
            if not isinstance(preapproval, Preapproval):
                raise ValueError("preapproval must be an instance of "
                                 "Preapproval")

            key = preapproval.preapproval_key
            endpoint_kwargs.update({'preapprovalKey': key})

        # Append extra arguments
        endpoint_kwargs.update(kwargs)

        # Call endpoint
        res, endpoint = self.call(api.Pay, **endpoint_kwargs)

        self.pay_key = endpoint.paykey

        if endpoint.status == 'ERROR':
            self.status = 'error'
            if 'payErrorList' in endpoint.response:
                if 'payError' in endpoint.response['payErrorList']:
                    payError = endpoint.response[
                        'payErrorList']['payError'][0]['error']
                    self.status_detail = "%s %s: %s" % (
                        payError['severity'],
                        payError['errorId'],
                        payError['message'])
                else:
                    self.status_detail = json.dumps(
                        endpoint.response.payErrorList,
                        cls=DjangoJSONEncoder,
                        )

        elif endpoint.status == 'COMPLETED':
            self.status = 'completed'
        elif endpoint.paykey or endpoint.status == 'CREATED':
            self.status = 'created'
        else:
            self.status = 'error'

        self.save()

        return self.status in ['created', 'completed']

    @transaction.atomic
    def refund(self):
        """Refund this payment"""

        # TODO: flow should create a Refund object and call Refund.process()

        self.save()

        if self.status != 'completed':
            raise ValueError('Cannot refund a Payment until it is completed.')

        res, refund_call = self.call(api.Refund, self.pay_key)

        self.status = 'refunded'
        self.save()

        refund = Refund(payment=self,
                        debug_request=json.dumps(
                            refund_call.data,
                            cls=DjangoJSONEncoder,
                            ),
                        debug_response=refund_call.raw_response,
                        )
        refund.save()

    def get_update_kwargs(self):
        if not self.pay_key:
            raise ValueError("Can't update unprocessed payments")
        return {'payKey': self.pay_key}

    def _parse_update_status(self, response):
        status = response.get('status', None)

        if status == 'COMPLETED':
            return 'completed'
        elif status == 'CREATED':
            return 'created'
        elif status == 'ERROR':
            return 'error'
        else:
            return self.status

    def next_url(self):
        return ('%s?cmd=_ap-payment&paykey=%s'
                % (settings.PAYPAL_PAYMENT_HOST, self.pay_key))

    def __unicode__(self):
        return self.pay_key


class Refund(PaypalAdaptive):
    """Models a refund make using Paypal"""

    STATUS_CHOICES = (
        ('new', _(u'New')),
        ('created', _(u'Created')),
        ('error', _(u'Error')),
        ('canceled', _(u'Canceled')),
        ('returned', _(u'Returned')),
        ('completed', _(u'Completed')),
    )

    payment = models.OneToOneField(Payment)
    status = models.CharField(_(u'status'), max_length=10,
                              choices=STATUS_CHOICES, default='new')
    status_detail = models.TextField(_(u'detailed status'), blank=True)

    # TODO: finish model


class Preapproval(PaypalAdaptive):
    """Models a preapproval made using Paypal"""

    update_endpoint = api.PreapprovalDetails
    default_valid_range = timedelta(days=90)
    default_valid_date = lambda: (timezone.now() +
                                  Preapproval.default_valid_range)

    STATUS_CHOICES = (
        ('new', _(u'New')),
        ('created', _(u'Created')),
        ('error', _(u'Error')),
        ('canceled', _(u'Canceled')),
        ('approved', _(u'Approved')),
        ('used', _(u'Used')),
        ('returned', _(u'Returned')),
    )

    valid_until_date = models.DateTimeField(_(u'valid until'),
                                            default=default_valid_date)
    preapproval_key = models.CharField(_(u'preapprovalkey'), max_length=255)
    status = models.CharField(_(u'status'), max_length=10,
                              choices=STATUS_CHOICES, default='new')
    status_detail = models.TextField(_(u'detailed status'), blank=True)

    def save(self, *args, **kwargs):
        is_new = self.id is None

        super(Preapproval, self).save(*args, **kwargs)

        if settings.USE_DELAYED_UPDATES and is_new:
            from .tasks import update_preapproval
            update_preapproval.apply_async(
                args=[self.id],
                eta=datetime.now() + settings.DELAYED_UPDATE_COUNTDOWN)

    @property
    def return_url(self):
        current_site = Site.objects.get_current()
        kwargs = {'preapproval_id': self.id, 'secret_uuid': self.secret_uuid}
        return_url = reverse('paypal-adaptive-preapproval-return',
                             kwargs=kwargs)
        return "%s://%s%s" % (get_http_protocol(), current_site, return_url)

    @property
    def cancel_url(self):
        current_site = Site.objects.get_current()
        kwargs = {'preapproval_id': self.id}
        cancel_url = reverse('paypal-adaptive-preapproval-cancel',
                             kwargs=kwargs)
        return "%s://%s%s" % (get_http_protocol(), current_site, cancel_url)

    @transaction.atomic
    def process(self, **kwargs):
        """Process the preapproval"""

        endpoint_kwargs = {'money': self.money,
                           'return_url': self.return_url,
                           'cancel_url': self.cancel_url,
                           'starting_date': self.created_date,
                           'ending_date': self.valid_until_date}

        if 'next' in kwargs:
            return_next = "%s?next=%s" % (self.return_url, kwargs.pop('next'))
            endpoint_kwargs.update({'return_url': return_next})

        if 'cancel' in kwargs:
            return_cancel = "%s?next=%s" % (self.cancel_url,
                                            kwargs.pop('cancel'))
            endpoint_kwargs.update({'cancel_url': return_cancel})

        if settings.USE_IPN:
            endpoint_kwargs.update({'ipn_url': self.ipn_url})

        # Append extra arguments
        endpoint_kwargs.update(**kwargs)

        res, preapprove = self.call(api.Preapprove, **endpoint_kwargs)

        if preapprove.preapprovalkey:
            self.preapproval_key = preapprove.preapprovalkey
            self.status = 'created'
        else:
            self.status = 'error'

        self.save()

        return self.status == 'created'

    @transaction.atomic
    def cancel_preapproval(self):
        res, cancel = self.call(api.CancelPreapproval,
                                preapproval_key=self.preapproval_key)

        # TODO: validate response

        self.status = 'canceled'
        self.save()
        return self.status == 'canceled'

    @transaction.atomic
    def mark_as_used(self):
        self.status = 'used'
        self.save()

        return self.status == 'used'

    def get_update_kwargs(self):
        if self.preapproval_key is None:
            raise ValueError("Can't update unprocessed preapprovals")
        return {'preapprovalKey': self.preapproval_key}

    def _parse_update_status(self, response):
        completed_payments = response.get('curPayments', None)
        max_payments = response.get('maxNumberOfPayments', None)
        status = response.get('status', None)
        approved = response.get('approved', 'false')

        if ('curPayments' in response and 'maxNumberOfPayments' in response
                and completed_payments == max_payments):
            return 'used'
        elif status == 'ACTIVE' and approved == 'true':
            return 'approved'
        elif status == 'ACTIVE':
            return 'created'
        elif status == 'CANCELED':
            return 'canceled'
        else:
            return self.status

    def next_url(self):
        """Custom next URL"""
        return ('%s?cmd=_ap-preapproval&preapprovalkey=%s'
                % (settings.PAYPAL_PAYMENT_HOST, self.preapproval_key))

    def __unicode__(self):
        return self.preapproval_key


class IPNLog(models.Model):
    created_date = models.DateTimeField(_(u'created on'), auto_now_add=True)
    path = models.TextField()
    post = models.TextField()
    verify_request_response = models.TextField()
    return_status_code = models.SmallIntegerField(blank=True, null=True)
    duration = models.PositiveIntegerField(blank=True, null=True)  # in seconds

    class Meta:
        verbose_name = _(u"IPN Log")
        verbose_name_plural = _(u"IPN Log")

    def post_to_dict(self):
        from paypaladaptive.api.ipn import IPN

        data = ast.literal_eval(self.post)
        transactions = IPN.process_transactions(data)
        for k,v in data.items():
            if k.startswith("transaction["):
                del data[k]
        data['transactions'] = [tr.to_dict() for tr in transactions]
        return data

    def post_to_json(self):
        return json.dumps(self.post_to_dict(), cls=DjangoJSONEncoder)
