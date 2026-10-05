# Technician assignment WhatsApp alerts

The backend attempts delivery immediately after the booking assignment transaction commits. Customer SMS and Firebase login OTP are unchanged. An opted-in technician is notified on a new assignment or reassignment, but not when the same active assignment is saved again.

## MSG91 setup

Connect your WhatsApp Business number to MSG91 and create an approved utility template named, for example, `technician_assignment`. Use a text-only body with these eight numbered placeholders, in this exact order:

```text
Hello {{1}}, a Purple Squad job has been assigned to you.
Booking: {{2}}
Service: {{3}}
Schedule: {{4}}
Customer: {{5}}
Contact: {{6}}
Address: {{7}}
Directions: {{8}}
Please check your technician dashboard for the latest job status.
```

Match the actual approved template name, language, and namespace in your MSG91 account. This implementation sends `body_1` through `body_8`, without header or button components. MSG91 documentation:

- https://docs.msg91.com/whatsapp/template-bulk
- https://msg91.com/help/whatsapp/send-whatsapp

## Backend environment variables

```dotenv
MSG91_WHATSAPP_ENABLED=true
MSG91_WHATSAPP_AUTH_KEY=<MSG91_AUTH_KEY_WITH_WHATSAPP_ACCESS>
MSG91_WHATSAPP_INTEGRATED_NUMBER=<CONNECTED_BUSINESS_NUMBER_WITH_COUNTRY_CODE>
MSG91_WHATSAPP_TECHNICIAN_TEMPLATE=technician_assignment
MSG91_WHATSAPP_TEMPLATE_NAMESPACE=<NAMESPACE_FROM_MSG91_IF_REQUIRED>
MSG91_WHATSAPP_TEMPLATE_LANGUAGE=en
```

Store the auth key in Secret Manager, not Git or frontend variables. A blank WhatsApp auth key falls back to the existing `MSG91_AUTH_KEY`. Leave the namespace empty if your MSG91 template does not require it. No change to `NOTIFICATION_PROVIDER` is needed: WhatsApp uses the separate `WHATSAPP_NOTIFICATION_PROVIDER`, defaulting to `apps.notifications.providers.Msg91WhatsAppNotificationProvider`.

The default endpoint is `https://control.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/`. Override `MSG91_WHATSAPP_FLOW_URL` only if your account's documented API endpoint differs.

## Deployment and activation

1. Deploy the backend and run migrations before switching traffic. New migrations: notifications `0008_whatsapp_channel` and technicians `0004_technician_whatsapp_notifications_enabled`.
2. Deploy the frontend for the opt-in checkbox.
3. In Admin → Technicians → Edit profile, enable WhatsApp assignment alerts only after the technician agrees to receive them. Existing technicians default to disabled.
4. Assign a confirmed booking. In Admin → Notifications, check the WHATSAPP entry and MSG91's delivery logs. The recipient should be the assigned technician, not the customer.

Provider acceptance is recorded as SENT, not confirmed DELIVERED. Actual delivery depends on WhatsApp, template approval, account configuration, and the recipient. No delivery webhook or automatic retries are added here. Failed attempts remain FAILED and can be retried from the existing admin notification controls after resolving the issue. Retrying an obsolete assignment is blocked; customer details should not be sent to a previously assigned technician.

Notifications are synchronous in the existing application, with a 10-second provider timeout. Failure does not undo the assignment. For high-volume dispatch, a durable background outbox/worker is a separate improvement; current delivery is not a guarantee of exactly-once receipt in the event of provider timeouts or process crashes.
