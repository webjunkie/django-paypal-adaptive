"""
Paypal Adaptive Payments supporting views

"""
import logging
import time

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import (HttpResponseServerError, HttpResponseRedirect,
                         HttpResponseBadRequest, HttpResponse, Http404)
from django.shortcuts import render_to_response
from django.template.context import RequestContext
from django.shortcuts import get_object_or_404
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import settings
from .api.ipn import constants
from .models import Payment, Preapproval
from .decorators import takes_ipn


logger = logging.getLogger(__name__)


def render(request, template, template_vars=None):
    if template_vars is None:
        template_vars = {}

    if request.GET.get('next'):
        return HttpResponseRedirect(request.GET.get('next'))

    context = RequestContext(request)
    d = {"is_embedded": settings.USE_EMBEDDED}
    d.update(template_vars)

    return render_to_response(template, d, context)


@login_required
@transaction.atomic
def payment_cancel(request, payment_id, secret_uuid,
                   template="paypaladaptive/cancel.html"):
    """Handle incoming cancellation from paypal"""
    logger.debug("Cancellation received for Payment %s", payment_id)

    payment = get_object_or_404(Payment, id=payment_id,
                                secret_uuid=secret_uuid)

    if payment.status in ('completed',):
        return HttpResponseBadRequest('Already completed.')

    payment.status = 'canceled'
    payment.save()

    template_vars = {"is_embedded": settings.USE_EMBEDDED}
    return render(request, template, template_vars)


@transaction.atomic
def payment_return(request, payment_id, secret_uuid,
                   template="paypaladaptive/return.html"):
    """
    Incoming return from Paypal process. Note that this is a user returning to
    the site and not a returned payment.

    """
    logger.debug("Return received for Payment %s", payment_id)

    payment = get_object_or_404(Payment, id=payment_id,
                                secret_uuid=secret_uuid)

    if secret_uuid != payment.secret_uuid:
        payment.status_detail = (_(u"BuyReturn secret \"%s\" did not match")
                                 % secret_uuid)
        payment.status = 'error'
        payment.save()
        return HttpResponseServerError('Unexpected error')

    elif payment.status not in ['created', 'completed']:
        payment.status_detail = _(u"Expected status to be created or "
                                  u"completed, not %s - duplicate "
                                  u"transaction?") % payment.status
        payment.status = 'error'
        payment.save()
        return HttpResponseServerError('Unexpected error')

    if payment.status != 'completed':
        payment.status = 'returned'
        payment.save()

    if settings.USE_DELAYED_UPDATES:
        from .tasks import update_payment
        update_payment.delay(payment_id=payment.id)

    template_vars = {"is_embedded": settings.USE_EMBEDDED}
    return render(request, template, template_vars)


@transaction.atomic
def preapproval_cancel(request, preapproval_id,
                       template="paypaladaptive/cancel.html"):
    """Incoming preapproval cancellation from paypal"""

    logger.debug("Cancellation received for Preapproval %s", preapproval_id)

    get_object_or_404(Preapproval, id=preapproval_id)

    template_vars = {"is_embedded": settings.USE_EMBEDDED}
    return render(request, template, template_vars)


@transaction.atomic
def preapproval_return(request, preapproval_id, secret_uuid,
                       template="paypaladaptive/return.html"):
    """
    Incoming return from paypal process (note this is a return to the site,
    not a returned payment)

    """

    preapproval = get_object_or_404(Preapproval, id=preapproval_id)

    logger.info("Return received for Preapproval %s", preapproval_id)

    if preapproval.status not in ['created', 'approved']:
        preapproval.status_detail = _(
            u"Expected status to be created or approved not %s - duplicate "
            u"transaction?") % preapproval.status
        preapproval.status = 'error'
        preapproval.save()
        return HttpResponseServerError('Unexpected error')

    elif secret_uuid != preapproval.secret_uuid:
        preapproval.status_detail = _(u"BuyReturn secret \"%s\" did not"
                                      u" match") % secret_uuid
        preapproval.status = 'error'
        preapproval.save()
        return HttpResponseServerError('Unexpected error')

    if preapproval.status != 'approved':
        preapproval.status = 'returned'
        preapproval.save()

    if settings.USE_DELAYED_UPDATES:
        from .tasks import update_preapproval
        update_preapproval.delay(preapproval_id=preapproval.id)

    template_vars = {"is_embedded": settings.USE_EMBEDDED,
                     "preapproval": preapproval, }
    return render(request, template, template_vars)


@csrf_exempt
@require_POST
@transaction.atomic
@takes_ipn
def ipn(request, object_id, object_secret_uuid, ipn):
    """
    Incoming IPN POST request from PayPal
    """
    object_class = {
        constants.IPN_TYPE_PAYMENT: Payment,
        constants.IPN_TYPE_PREAPPROVAL: Preapproval,
        constants.IPN_TYPE_ADJUSTMENT: Payment
    }.get(ipn.type, None)

    if object_class is None:
        obj = None
        for model in (Payment, Preapproval):
            try:
                obj = model.objects.get(pk=object_id)
            except model.DoesNotExist:
                continue
        if obj is None:
            logger.warning(
                'No transaction type was specified and could not find ID %s, '
                'replying to IPN with 404.',
                object_id,
                )
            raise Http404
    else:
        try:
            obj = object_class.objects.get(pk=object_id)
        except object_class.DoesNotExist:
            logger.warning('Could not find %s ID %s, replying to IPN with '
                           '404.', object_class.__name__, object_id)
            raise Http404

    obj.sender_email = ipn.sender_email

    if obj.secret_uuid != object_secret_uuid:
        obj.status = 'error'
        obj.status_detail = ('IPN secret "%s" did not match db'
                             % object_secret_uuid)
        logger.info("Error detail: %s", obj.status_detail)
        obj.save()
        return HttpResponseBadRequest()

    # IPN type-specific operations
    if ipn.type == constants.IPN_TYPE_PAYMENT:

        # if obj.pay_key != ipn.pay_key:
        #     obj.status = 'error'
        #     obj.status_detail = ('Pay Key mismatch: %s != %s', obj.pay_key, ipn.pay_key)
        #     logger.debug("Error detail: %s", obj.status_detail)
        #     obj.save()
        #     return HttpResponseBadRequest()

        ipn_total_money = ipn.get_transactions_total_money()
        if obj.money != ipn_total_money:
            obj.status = 'error'
            obj.status_detail = ("IPN amounts didn't match. Payment requested "
                                 "%s. Payment made %s"
                                 % (obj.money, ipn_total_money))
            logger.info("Error detail: %s", obj.status_detail)

        # check payment status
        elif ipn.status != 'COMPLETED':
            obj.status = 'error'
            obj.status_detail = ('PayPal status was "%s"' % ipn.status)
            logger.info("Error detail: %s", obj.status_detail)
        else:
            obj.status = 'completed'

            # TODO: mark preapproval 'used'
    elif ipn.type == constants.IPN_TYPE_PREAPPROVAL:
        if obj.money != ipn.max_total_amount_of_all_payments:
            obj.status = 'error'
            obj.status_detail = (
                "IPN amounts didn't match. Preapproval requested %s. "
                "Preapproval made %s"
                % (obj.money, ipn.max_total_amount_of_all_payments))
            logger.info("Error detail: %s", obj.status_detail)
        elif ipn.status == constants.IPN_STATUS_CANCELED:
            obj.status = 'canceled'
            obj.status_detail = 'Cancellation received via IPN'
            logger.debug("Canceled detail: %s", obj.status_detail)
        elif not ipn.approved:
            obj.status = 'error'
            obj.status_detail = "The preapproval is not approved"
            logger.debug("Error detail: %s", obj.status_detail)
        else:
            obj.status = 'approved'
    else:
        logger.warning(
            'No action found for IPN Type "%s" with '
            'status "%s" (id: "%s", secret_uuid: %s)',
            ipn.type, ipn.status, obj.id, obj.secret_uuid
            )

    obj.save()

    status_code = 204  # 200
    if ipn.ipn_log is not None:
        ipn_log = ipn.ipn_log
        ipn_log.return_status_code = status_code
        if ipn_log._start_time:
            ipn_log.duration = time.time() - ipn_log._start_time
        ipn_log.save()

    return HttpResponse(status=status_code)

