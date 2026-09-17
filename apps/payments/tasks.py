import logging

from apps.payments.models import Payment, PaymentRecordStatus, PaymentType
from apps.payments.services import reconcile_refund


logger = logging.getLogger(__name__)


def reconcile_refund_task(refund_id):
    """Reconcile one refund synchronously."""
    reconcile_refund(refund_id=refund_id)


def reconcile_pending_refunds():
    """Reconcile pending refunds synchronously when invoked manually."""
    refund_ids = Payment.objects.filter(
        payment_type=PaymentType.REFUND,
        status__in=[PaymentRecordStatus.CREATED, PaymentRecordStatus.PENDING],
        provider_refund_id__isnull=False,
    ).values_list("id", flat=True)[:500]
    queued = 0
    for refund_id in refund_ids:
        reconcile_refund_task(str(refund_id))
        queued += 1
    logger.info("Reconciled %s pending refunds", queued)
    return queued
