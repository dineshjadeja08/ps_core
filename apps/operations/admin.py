from datetime import timedelta

from django.contrib import admin
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.audit.models import AuditAction
from apps.audit.services import audit_event
from apps.bookings.models import Booking, BookingStatus, PaymentStatus
from apps.notifications.models import Notification, NotificationStatus
from apps.operations.models import (
    ACTIVE_LEAD_STATUSES,
    FAQ,
    HomepageBanner,
    HomepageBannerPlacement,
    Lead,
    LeadStatus,
    LeadStatusHistory,
)
from apps.payments.models import Payment, PaymentRecordStatus


class LeadStatusHistoryInline(admin.TabularInline):
    model = LeadStatusHistory
    extra = 0
    can_delete = False
    readonly_fields = ("from_status", "to_status", "changed_by", "notes", "created_at", "updated_at")
    fields = readonly_fields


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = (
        "customer_name",
        "primary_mobile",
        "required_service",
        "city",
        "pincode",
        "source",
        "status_badge",
        "assigned_staff",
        "follow_up_at",
        "converted_booking_link",
        "created_at",
    )
    list_filter = ("source", "status", "required_service", "assigned_staff", "pincode", "created_at", "follow_up_at")
    search_fields = ("customer_name", "primary_mobile", "alternate_mobile", "email", "pincode", "converted_booking__booking_number")
    date_hierarchy = "created_at"
    autocomplete_fields = ("required_service", "assigned_staff", "converted_booking")
    readonly_fields = ("created_by", "created_at", "updated_at", "converted_booking_link")
    inlines = (LeadStatusHistoryInline,)
    fieldsets = (
        ("Customer", {"fields": ("customer_name", "primary_mobile", "alternate_mobile", "email")}),
        ("Need", {"fields": ("required_service", "package", "address", "city", "pincode")}),
        ("Lead management", {"fields": ("source", "status", "assigned_staff", "preferred_callback_at", "follow_up_at")}),
        ("Notes", {"fields": ("customer_notes", "internal_notes")}),
        ("Conversion", {"fields": ("converted_booking", "converted_booking_link")}),
        ("System", {"fields": ("created_by", "created_at", "updated_at")}),
    )
    actions = ("mark_contacted", "mark_interested", "mark_follow_up", "mark_lost", "mark_closed")
    list_select_related = ("required_service", "assigned_staff", "converted_booking", "created_by")

    @admin.display(description="Status")
    def status_badge(self, obj):
        classes = {
            LeadStatus.NEW: "#2563eb",
            LeadStatus.CONTACTED: "#7c3aed",
            LeadStatus.INTERESTED: "#16a34a",
            LeadStatus.FOLLOW_UP: "#ca8a04",
            LeadStatus.CONVERTED: "#15803d",
            LeadStatus.LOST: "#dc2626",
            LeadStatus.CLOSED: "#64748b",
        }
        color = classes.get(obj.status, "#64748b")
        return format_html(
            '<span style="border-radius:999px;background:{};color:white;padding:3px 9px;font-size:12px;font-weight:700;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Booking")
    def converted_booking_link(self, obj):
        if not obj.converted_booking_id:
            return "-"
        url = reverse("admin:bookings_booking_change", args=[obj.converted_booking_id])
        return format_html('<a href="{}">{}</a>', url, obj.converted_booking.booking_number)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("required_service", "assigned_staff", "converted_booking", "created_by")

    def save_model(self, request, obj, form, change):
        previous_status = None
        if change and obj.pk:
            previous_status = Lead.objects.filter(pk=obj.pk).values_list("status", flat=True).first()
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        obj.full_clean()
        super().save_model(request, obj, form, change)

        if not change:
            LeadStatusHistory.objects.create(
                lead=obj,
                from_status="",
                to_status=obj.status,
                changed_by=request.user,
                notes="Lead created.",
            )
            audit_event(
                action=AuditAction.LEAD_CREATED,
                actor=request.user,
                request=request,
                resource_type="lead",
                resource_id=obj.id,
                metadata={"source": obj.source, "status": obj.status},
            )
            return

        action = AuditAction.LEAD_UPDATED
        metadata = {"status": obj.status}
        if previous_status and previous_status != obj.status:
            LeadStatusHistory.objects.create(
                lead=obj,
                from_status=previous_status,
                to_status=obj.status,
                changed_by=request.user,
                notes=obj.internal_notes,
            )
            action = AuditAction.LEAD_STATUS_CHANGED
            metadata["from_status"] = previous_status
            if obj.status == LeadStatus.CONVERTED:
                action = AuditAction.LEAD_CONVERTED
        audit_event(
            action=action,
            actor=request.user,
            request=request,
            resource_type="lead",
            resource_id=obj.id,
            metadata=metadata,
        )

    def _bulk_status(self, request, queryset, status, label):
        count = 0
        for lead in queryset.exclude(status=status):
            previous = lead.status
            lead.status = status
            lead.full_clean()
            lead.save(update_fields=["status", "updated_at"])
            LeadStatusHistory.objects.create(
                lead=lead,
                from_status=previous,
                to_status=status,
                changed_by=request.user,
                notes=f"Marked {label} from admin list.",
            )
            audit_event(
                action=AuditAction.LEAD_STATUS_CHANGED,
                actor=request.user,
                request=request,
                resource_type="lead",
                resource_id=lead.id,
                metadata={"from_status": previous, "status": status},
            )
            count += 1
        self.message_user(request, f"{count} leads marked {label}.")

    @admin.action(description="Mark selected leads as contacted")
    def mark_contacted(self, request, queryset):
        self._bulk_status(request, queryset, LeadStatus.CONTACTED, "contacted")

    @admin.action(description="Mark selected leads as interested")
    def mark_interested(self, request, queryset):
        self._bulk_status(request, queryset, LeadStatus.INTERESTED, "interested")

    @admin.action(description="Mark selected leads for follow-up")
    def mark_follow_up(self, request, queryset):
        self._bulk_status(request, queryset, LeadStatus.FOLLOW_UP, "follow-up")

    @admin.action(description="Mark selected leads as lost")
    def mark_lost(self, request, queryset):
        self._bulk_status(request, queryset, LeadStatus.LOST, "lost")

    @admin.action(description="Mark selected leads as closed")
    def mark_closed(self, request, queryset):
        self._bulk_status(request, queryset, LeadStatus.CLOSED, "closed")


@admin.register(LeadStatusHistory)
class LeadStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("lead", "from_status", "to_status", "changed_by", "created_at")
    list_filter = ("to_status", "created_at")
    search_fields = ("lead__customer_name", "lead__primary_mobile", "notes")
    readonly_fields = ("lead", "from_status", "to_status", "changed_by", "notes", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(HomepageBanner)
class HomepageBannerAdmin(admin.ModelAdmin):
    list_display = ("title", "placement", "display_order", "is_active", "is_live_badge", "starts_at", "ends_at", "updated_at")
    list_filter = ("placement", "is_active", "starts_at", "ends_at")
    search_fields = ("title", "description", "button_text", "button_link", "image_alt_text")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "updated_at", "desktop_preview", "mobile_preview")
    fieldsets = (
        ("Content", {"fields": ("title", "description", "image_alt_text")}),
        ("Images", {"fields": ("desktop_image", "desktop_preview", "mobile_image", "mobile_preview")}),
        ("Button", {"fields": ("button_text", "button_link")}),
        ("Publishing", {"fields": ("placement", "display_order", "starts_at", "ends_at", "is_active")}),
        ("System", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Live")
    def is_live_badge(self, obj):
        color = "#16a34a" if obj.is_live else "#64748b"
        label = "Live" if obj.is_live else "Hidden"
        return format_html(
            '<span style="border-radius:999px;background:{};color:white;padding:3px 9px;font-size:12px;font-weight:700;">{}</span>',
            color,
            label,
        )

    @admin.display(description="Desktop preview")
    def desktop_preview(self, obj):
        if not obj.desktop_image:
            return "-"
        return format_html('<img src="{}" style="max-width:220px;max-height:120px;border-radius:8px;" />', obj.desktop_image.url)

    @admin.display(description="Mobile preview")
    def mobile_preview(self, obj):
        if not obj.mobile_image:
            return "-"
        return format_html('<img src="{}" style="max-width:120px;max-height:120px;border-radius:8px;" />', obj.mobile_image.url)

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        super().save_model(request, obj, form, change)
        audit_event(
            action=AuditAction.BANNER_UPDATED if change else AuditAction.BANNER_CREATED,
            actor=request.user,
            request=request,
            resource_type="homepage_banner",
            resource_id=obj.id,
            metadata={"placement": obj.placement, "is_active": obj.is_active},
        )


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ("question", "category", "service", "display_order", "is_active", "updated_at")
    list_filter = ("is_active", "category", "service")
    search_fields = ("question", "answer", "category__name", "service__name", "package")
    autocomplete_fields = ("category", "service")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("FAQ", {"fields": ("question", "answer", "category", "service", "package")}),
        ("Display", {"fields": ("display_order", "is_active")}),
        ("System", {"fields": ("created_at", "updated_at")}),
    )

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        super().save_model(request, obj, form, change)
        audit_event(
            action=AuditAction.FAQ_UPDATED if change else AuditAction.FAQ_CREATED,
            actor=request.user,
            request=request,
            resource_type="faq",
            resource_id=obj.id,
            metadata={"is_active": obj.is_active},
        )


def build_operations_dashboard_context():
    now = timezone.now()
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    upcoming_cutoff = today + timedelta(days=7)
    payments_today = (
        Payment.objects.filter(status=PaymentRecordStatus.SUCCESS, paid_at__date=today).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    cards = [
        ("Leads created today", Lead.objects.filter(created_at__date=today).count(), reverse("admin:operations_lead_changelist")),
        ("New leads", Lead.objects.filter(status=LeadStatus.NEW).count(), reverse("admin:operations_lead_changelist") + "?status__exact=NEW"),
        ("Follow-ups due today", Lead.objects.filter(follow_up_at__date=today, status__in=ACTIVE_LEAD_STATUSES).count(), reverse("admin:operations_lead_changelist")),
        ("Bookings created today", Booking.objects.filter(created_at__date=today).count(), reverse("admin:bookings_booking_changelist")),
        ("Confirmed bookings", Booking.objects.filter(booking_status=BookingStatus.CONFIRMED).count(), reverse("admin:bookings_booking_changelist") + "?booking_status__exact=CONFIRMED"),
        ("Payment-pending bookings", Booking.objects.filter(payment_status=PaymentStatus.UNPAID).count(), reverse("admin:bookings_booking_changelist") + "?payment_status__exact=UNPAID"),
        ("Payments received today", f"INR {payments_today}", reverse("admin:payments_payment_changelist")),
        ("Awaiting technician", Booking.objects.filter(booking_status=BookingStatus.CONFIRMED, assigned_technician__isnull=True).count(), reverse("admin:bookings_booking_changelist")),
        ("Upcoming services", Booking.objects.filter(service_date__gte=tomorrow, service_date__lte=upcoming_cutoff).exclude(booking_status=BookingStatus.CANCELLED).count(), reverse("admin:bookings_booking_changelist")),
        ("Cancelled bookings", Booking.objects.filter(booking_status=BookingStatus.CANCELLED).count(), reverse("admin:bookings_booking_changelist") + "?booking_status__exact=CANCELLED"),
    ]
    return {
        "cards": [{"label": label, "value": value, "url": url} for label, value, url in cards],
        "recent_leads": Lead.objects.select_related("required_service", "assigned_staff").order_by("-created_at")[:5],
        "recent_bookings": Booking.objects.select_related("customer", "service", "assigned_technician").order_by("-created_at")[:5],
        "payment_pending_bookings": Booking.objects.select_related("customer", "service").filter(payment_status=PaymentStatus.UNPAID).order_by("-created_at")[:5],
        "followups_due": Lead.objects.select_related("required_service", "assigned_staff").filter(follow_up_at__lte=now, status__in=ACTIVE_LEAD_STATUSES).order_by("follow_up_at")[:5],
        "unassigned_bookings": Booking.objects.select_related("customer", "service").filter(booking_status=BookingStatus.CONFIRMED, assigned_technician__isnull=True).order_by("service_date")[:5],
        "failed_notifications": Notification.objects.select_related("recipient", "booking").filter(status=NotificationStatus.FAILED).order_by("-created_at")[:5],
        "quick_actions": [
            ("Create lead", reverse("admin:operations_lead_add")),
            ("Create booking", reverse("admin:bookings_booking_add")),
            ("Send payment link", reverse("admin:bookings_booking_changelist") + "?payment_status__exact=UNPAID"),
            ("Assign technician", reverse("admin:bookings_booking_changelist") + "?booking_status__exact=CONFIRMED"),
            ("Add service", reverse("admin:catalogue_service_add")),
            ("Add package", reverse("admin:catalogue_service_add")),
            ("Add homepage banner", reverse("admin:operations_homepagebanner_add")),
        ],
        "banner_placements": HomepageBannerPlacement.choices,
    }


def operations_admin_index(request, extra_context=None):
    context = dict(extra_context or {})
    if request.user.has_perm("operations.view_lead"):
        context["operations_dashboard"] = build_operations_dashboard_context()
    return admin.site._operations_original_index(request, context)


if not getattr(admin.site, "_operations_dashboard_installed", False):
    admin.site._operations_original_index = admin.site.index
    admin.site.index_template = "admin/operations_index.html"
    admin.site.index = operations_admin_index
    admin.site._operations_dashboard_installed = True
