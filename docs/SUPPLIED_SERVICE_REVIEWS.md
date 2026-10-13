# Supplied service reviews

After deploying the updated backend, first preview the replacement inside the backend container or a Cloud Run job configured with the same production settings, database secret and VPC networking:

```sh
python manage.py import_supplied_service_reviews --dry-run
```

Back up the database and check the previewed counts, then apply:

```sh
python manage.py import_supplied_service_reviews
```

No schema migration is required. The command removes only the previous importer-created review IDs, then adds all 110 rows from the business-provided review workbook to matching active services. Some service groups have more than five reviews. AC chemical wash, gas refill, and general washing-machine service names have explicit aliases. The command reports workbook groups without a matching active service; it does not invent a destination for them.

These are admin-managed service reviews, not verified booking reviews. The importer does not invent bookings, customer accounts, or original review dates. Customer-submitted booking reviews and manually added admin reviews are preserved. The frontend shows five reviews first on a service page and offers a read-more control for additional reviews. Import timestamps are not presented as original customer review dates.

Repeated imports do not duplicate the same records or overwrite admin edits/visibility. Use Admin → Reviews for moderation afterward. Re-running the importer after deleting an imported review will recreate it; hide it instead if you intend to re-import. This is an explicit import, not an automatic startup command.

Deploy the frontend separately to publish the redesigned review cards.
