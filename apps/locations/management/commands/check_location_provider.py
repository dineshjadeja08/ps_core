import time
from uuid import uuid4

from django.core.management.base import BaseCommand, CommandError

from apps.locations.providers import LocationProviderError, get_location_provider


class Command(BaseCommand):
    help = "Check the configured location provider with one autocomplete and one reverse-geocode lookup."

    def handle(self, *args, **options):
        provider = get_location_provider()
        checks = (
            ("autocomplete", lambda request_id: provider.get_autocomplete("avadi", city="Chennai", request_id=request_id)),
            ("reverse-geocode", lambda request_id: provider.get_reverse_geocode(13.0827, 80.2707, request_id=request_id)),
        )
        failed = False
        for name, lookup in checks:
            request_id = str(uuid4())
            started = time.monotonic()
            try:
                result = lookup(request_id)
            except LocationProviderError as exc:
                failed = True
                latency = exc.latency_ms if exc.latency_ms is not None else round((time.monotonic() - started) * 1000)
                self.stderr.write(
                    f"{name}: FAILED status={exc.status_code or exc.reason} latency_ms={latency} "
                    f"request_id={exc.request_id or request_id} body={exc.response_snippet or '<empty>'}"
                )
            else:
                latency = round((time.monotonic() - started) * 1000)
                size = len(result) if isinstance(result, list) else 1
                self.stdout.write(self.style.SUCCESS(f"{name}: OK status=200 latency_ms={latency} results={size} request_id={request_id}"))

        if failed:
            raise CommandError("One or more location-provider checks failed. See the sanitized diagnostics above.")
