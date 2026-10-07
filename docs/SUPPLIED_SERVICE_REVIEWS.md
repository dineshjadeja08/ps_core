# Supplied service reviews

After deploying the updated backend, run this once inside the backend container or a Cloud Run job configured with the same production settings, database secret and VPC networking:

```sh
python manage.py import_supplied_service_reviews
```

No schema migration is required. This command adds five supplied reviews per active AC and washing-machine service. AC installation/removal feedback is matched to relevant packages; general AC feedback is distributed in groups of five. Other service families and existing reviews are not changed.

These are admin-managed service reviews, not verified booking reviews. The importer does not invent bookings, customer accounts, or original review dates. The frontend shows up to five reviews with the supplied names, comments and ratings. Import timestamps are not presented as original customer review dates.

Repeated imports do not duplicate the same records or overwrite admin edits/visibility. Use Admin → Reviews for moderation afterward. Re-running the importer after deleting an imported review will recreate it; hide it instead if you intend to re-import. Newly added/reordered service slugs can change the general-feedback allocation, so this is an explicit one-time import, not an automatic startup command.

Deploy the frontend separately to publish the redesigned review cards.
