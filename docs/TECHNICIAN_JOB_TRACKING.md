# Technician job updates and customer booking tracking

## Workflow

Technicians open `/technician/jobs` using their existing technician login. Only active, verified, employed technicians can see and update their currently assigned jobs. Active jobs and job history have separate paginated lists.

The buttons follow this sequence:

`TECHNICIAN_ASSIGNED` → `TECHNICIAN_EN_ROUTE` → `TECHNICIAN_ARRIVED` → `IN_PROGRESS` → `COMPLETED`.

POST actions use `/api/v1/technician/jobs/<booking-id>/en-route/`, `arrived/`, `start/`, and `complete/`. A repeated action for the current state returns success without adding history or repeating notification events. Attempts to skip steps, move backwards, change cancelled/closed jobs, or update another technician's assignment are rejected. Assignment ownership and active profile eligibility are rechecked under the booking lock, not just when the request first looks up the job.

Admins retain their existing start/complete/cancel operations. The existing balance-payment requirement still applies before completion; technicians cannot bypass it. Completion triggers the existing review-request event. Arrival and start do not add new SMS or WhatsApp templates; existing notification configuration is unchanged.

## Customer tracking

The customer's `/bookings` list refreshes every 15 seconds while visible. `/bookings/<id>` displays the assigned technician's name and phone, a call button, six progress steps, recorded timestamps, and the existing status timeline. Active detail pages refresh every 15 seconds and on window focus; terminal booking states stop interval polling. Manual refresh is available. Failed background refreshes preserve the last received data and show a warning.

Tracking is technician-reported job status, not GPS location or an arrival-time estimate. Customers can retrieve only their own bookings. Admin booking details and activity timelines also refresh every 15 seconds.

## Deployment

Deploy the backend without traffic, update the existing migration job to that exact new image, and run `/app/scripts/cloud-run-migrate.sh` successfully before switching traffic. This release adds `bookings/0007_booking_technician_arrived.py`. Deploy the frontend afterwards. No new environment variables or provider credentials are required.

## Acceptance check

1. Assign a confirmed booking to an active, verified technician.
2. Log in as that technician and open the Active jobs tab.
3. On a separate customer device, open the booking detail page.
4. Press Start travelling, I have arrived, and Start service, checking that each update appears on the customer page within its next successful refresh (approximately 15 seconds).
5. Have the admin record outstanding balance when required; confirm and complete the service. Verify the completion timestamp, history entry, and existing review request.
6. Check the technician's Job history and the admin booking activity timeline.
7. Test an unassigned technician and a different customer: neither should be able to access the booking through their respective endpoints.
