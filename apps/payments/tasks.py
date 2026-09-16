import logging

from celery import shared_task

from apps.payments.models import Payment, PaymentRecordStatus, PaymentType
from apps.payments.services import reconcile_refund


logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
    max_retries=5,
    acks_late=True,
)
def reconcile_refund_task(self, refund_id):
    reconcile_refund(refund_id=refund_id)


@shared_task
def reconcile_pending_refunds():
    refund_ids = Payment.objects.filter(
        payment_type=PaymentType.REFUND,
        status__in=[PaymentRecordStatus.CREATED, PaymentRecordStatus.PENDING],
        provider_refund_id__isnull=False,
    ).values_list("id", flat=True)[:500]
    queued = 0
    for refund_id in refund_ids:
        reconcile_refund_task.delay(str(refund_id))
        queued += 1
    logger.info("Queued %s pending refunds for reconciliation", queued)
    return queued
