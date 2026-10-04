from django.db import migrations


PAGES = (
    {
        "service_slug": "ac-service-chennai",
        "service_name": "AC Service",
        "category_slug": "ac-services",
        "area": "",
        "area_slug": "",
        "meta_title": "AC Service in Chennai | Purple Squad",
        "meta_description": "Book AC service in Chennai with Purple Squad for cleaning, repair, gas refill, installation and doorstep support.",
        "h1": "AC Service & Repair in Chennai",
        "intro_content": "Purple Squad provides doorstep AC inspection, cleaning, repair, gas refill, installation and uninstallation across supported Chennai neighbourhoods. Choose the service you need, see the price before booking and schedule a verified professional for your address.",
        "pricing_intro": "Prices shown below come from the live Purple Squad catalogue. Any additional repair or spare-part cost is explained before work begins.",
        "coverage_areas": [],
        "faqs": [
            {"question": "Which AC services can I book in Chennai?", "answer": "Available options include inspection, foam-jet cleaning, chemical wash, gas refill, installation and uninstallation."},
            {"question": "Will I see the service price before booking?", "answer": "Yes. Current catalogue pricing is displayed before you continue to booking."},
        ],
    },
    {
        "service_slug": "washing-machine-repair-chennai",
        "service_name": "Washing Machine Repair",
        "category_slug": "washing-machine-services",
        "area": "",
        "area_slug": "",
        "meta_title": "Washing Machine Repair in Chennai | Purple Squad",
        "meta_description": "Book washing machine repair, installation and uninstallation in Chennai with clear pricing and doorstep support.",
        "h1": "Washing Machine Repair in Chennai",
        "intro_content": "Purple Squad handles washing, spinning, drainage and installation concerns for washing machines across supported Chennai addresses. A professional inspects the appliance, explains the work required and shares any repair estimate before proceeding.",
        "pricing_intro": "The listed inspection and installation prices are current catalogue prices; approved parts and additional repair work may cost extra.",
        "coverage_areas": [],
        "faqs": [
            {"question": "Do you repair washing machines at home?", "answer": "Yes. The initial diagnosis is completed at the service address whenever the appliance and fault allow it."},
            {"question": "Can I book installation after moving house?", "answer": "Yes. Installation and uninstallation options are available separately in the catalogue."},
        ],
    },
    {
        "service_slug": "refrigerator-repair-chennai",
        "service_name": "Refrigerator Repair",
        "category_slug": "refrigerator-services",
        "area": "",
        "area_slug": "",
        "meta_title": "Refrigerator Repair in Chennai | Purple Squad",
        "meta_description": "Book refrigerator inspection and repair support in Chennai for cooling, leakage, noise and electrical concerns.",
        "h1": "Refrigerator Repair in Chennai",
        "intro_content": "Purple Squad offers doorstep refrigerator inspection across supported Chennai locations for cooling loss, unusual noise, water leakage and electrical concerns. The technician checks the appliance and provides a repair estimate before additional work begins.",
        "pricing_intro": "The catalogue price covers the selected inspection or installation service. Parts and approved repairs are quoted separately when required.",
        "coverage_areas": [],
        "faqs": [
            {"question": "What refrigerator issues can be inspected?", "answer": "Common requests include poor cooling, leakage, unusual noise and electrical or installation concerns."},
            {"question": "Are spare parts included in the inspection price?", "answer": "No. Required parts and repair work are quoted after diagnosis and completed only after approval."},
        ],
    },
    {
        "service_slug": "water-purifier-service-chennai",
        "service_name": "Water Purifier Service",
        "category_slug": "home-appliances-repair",
        "area": "",
        "area_slug": "",
        "meta_title": "Water Purifier Service in Chennai | Purple Squad",
        "meta_description": "Book water purifier service in Chennai for RO and UV purifier leakage, low flow, filter alerts and maintenance support.",
        "h1": "Water Purifier Service in Chennai",
        "intro_content": "Purple Squad provides doorstep water purifier inspection and maintenance across supported Chennai addresses. Book help for RO or UV purifier leakage, low water flow, unusual taste, filter alerts and power concerns, with any required parts quoted after inspection.",
        "pricing_intro": "The catalogue price covers the selected inspection service. Filters, membranes, pumps and other approved replacement parts are quoted separately.",
        "coverage_areas": [],
        "faqs": [
            {"question": "Which water purifier issues can I book?", "answer": "You can request inspection for leakage, low flow, unusual taste, filter alerts and common electrical concerns."},
            {"question": "Are replacement filters included?", "answer": "No. Required filters, membranes or other parts are quoted after inspection and replaced only with approval."},
        ],
    },
    {
        "service_slug": "ac-service-chennai",
        "service_name": "AC Service",
        "category_slug": "ac-services",
        "area": "Velachery",
        "area_slug": "velachery",
        "meta_title": "AC Service in Velachery, Chennai | Purple Squad",
        "meta_description": "Book AC service in Velachery for cleaning, repair, gas refill and installation with clear pricing and doorstep support.",
        "h1": "AC Service & Repair in Velachery, Chennai",
        "intro_content": "Book doorstep AC service in Velachery for homes around Vijaya Nagar, Baby Nagar, Tansi Nagar, Ram Nagar and the Taramani Link Road side. Purple Squad supports routine cleaning, cooling diagnosis, gas-refill checks and installation work with pricing shown before booking.",
        "pricing_intro": "Choose from live AC service options below. Repair parts or extra work are quoted after inspection and require your approval.",
        "coverage_areas": ["Vijaya Nagar", "Baby Nagar", "Tansi Nagar", "Ram Nagar", "Taramani Link Road"],
        "faqs": [
            {"question": "Do you serve both sides of Velachery?", "answer": "Service is available across supported Velachery pincodes, including the Vijaya Nagar and Taramani Link Road surroundings."},
            {"question": "Can I book AC cleaning for an apartment?", "answer": "Yes. Select the appropriate cleaning option and provide the exact apartment address during booking."},
        ],
    },
    {
        "service_slug": "ac-service-chennai",
        "service_name": "AC Service",
        "category_slug": "ac-services",
        "area": "Tambaram",
        "area_slug": "tambaram",
        "meta_title": "AC Service in Tambaram, Chennai | Purple Squad",
        "meta_description": "Book AC service in Tambaram, including East Tambaram and nearby supported localities, with doorstep assistance.",
        "h1": "AC Service & Repair in Tambaram, Chennai",
        "intro_content": "Purple Squad provides AC cleaning, repair inspection, gas-refill checks and installation support around Tambaram, including East Tambaram, West Tambaram, Kadaperi, Irumbuliyur and nearby Selaiyur addresses that fall within active service pincodes.",
        "pricing_intro": "Current AC service prices are displayed below. The professional confirms any additional repair or material charge before starting it.",
        "coverage_areas": ["East Tambaram", "West Tambaram", "Kadaperi", "Irumbuliyur", "Selaiyur"],
        "faqs": [
            {"question": "Is AC service available in East Tambaram?", "answer": "Yes, when the entered address falls within an active Purple Squad service pincode."},
            {"question": "Can I arrange AC uninstallation before shifting?", "answer": "Yes. AC uninstallation is available as a separate service option and can be scheduled for your Tambaram address."},
        ],
    },
    {
        "service_slug": "ac-service-chennai",
        "service_name": "AC Service",
        "category_slug": "ac-services",
        "area": "Pallavaram",
        "area_slug": "pallavaram",
        "meta_title": "AC Service in Pallavaram, Chennai | Purple Squad",
        "meta_description": "Book AC cleaning, repair inspection, gas refill and installation in Pallavaram with Purple Squad.",
        "h1": "AC Service & Repair in Pallavaram, Chennai",
        "intro_content": "Residents in Pallavaram and nearby supported neighbourhoods can book Purple Squad for AC cleaning, fault inspection, gas-refill diagnosis, installation and uninstallation. Enter the exact service address so availability is checked against the active pincode list.",
        "pricing_intro": "The prices below reflect the live catalogue. If diagnosis identifies parts or extra repair work, the amount is shared for approval first.",
        "coverage_areas": ["Pallavaram", "Nagalkeni", "Chromepet", "Pammal", "Pozhichur"],
        "faqs": [
            {"question": "How is Pallavaram availability confirmed?", "answer": "Purple Squad checks the selected address pincode before the booking proceeds."},
            {"question": "Can I book both cleaning and a cooling check?", "answer": "Choose the service option that matches the requirement; the professional can explain additional findings during the visit."},
        ],
    },
    {
        "service_slug": "washing-machine-repair-chennai",
        "service_name": "Washing Machine Repair",
        "category_slug": "washing-machine-services",
        "area": "Velachery",
        "area_slug": "velachery",
        "meta_title": "Washing Machine Repair in Velachery | Purple Squad",
        "meta_description": "Book washing machine repair in Velachery for washing, spinning and drainage issues with doorstep inspection.",
        "h1": "Washing Machine Repair in Velachery, Chennai",
        "intro_content": "Purple Squad provides washing machine inspection in Velachery for machines that do not start, drain, spin or wash normally. Doorstep visits cover supported addresses around Vijaya Nagar, Baby Nagar, Tansi Nagar, Ram Nagar and nearby residential streets.",
        "pricing_intro": "The inspection charge is shown before booking. Parts and repair labour, when needed, are estimated after diagnosis.",
        "coverage_areas": ["Vijaya Nagar", "Baby Nagar", "Tansi Nagar", "Ram Nagar", "Dhandeeswaram"],
        "faqs": [
            {"question": "Can you inspect a washing machine that is not draining?", "answer": "Yes. Drainage and spinning faults are common inspection requests handled at the service address."},
            {"question": "Is installation also available in Velachery?", "answer": "Yes. Washing machine installation and uninstallation appear as separate bookable options."},
        ],
    },
    {
        "service_slug": "refrigerator-repair-chennai",
        "service_name": "Refrigerator Repair",
        "category_slug": "refrigerator-services",
        "area": "Velachery",
        "area_slug": "velachery",
        "meta_title": "Refrigerator Repair in Velachery | Purple Squad",
        "meta_description": "Book refrigerator inspection in Velachery for cooling, leakage, noise and electrical issues.",
        "h1": "Refrigerator Repair in Velachery, Chennai",
        "intro_content": "Book a refrigerator inspection in Velachery for reduced cooling, water leakage, unusual sounds or electrical concerns. Purple Squad serves supported homes around Vijaya Nagar, Baby Nagar, Tansi Nagar, Ram Nagar and the nearby Taramani corridor.",
        "pricing_intro": "The displayed inspection price covers diagnosis. Any parts or repair work are quoted separately before proceeding.",
        "coverage_areas": ["Vijaya Nagar", "Baby Nagar", "Tansi Nagar", "Ram Nagar", "Taramani Link Road"],
        "faqs": [
            {"question": "Can I book help for a refrigerator that is not cooling?", "answer": "Yes. Cooling loss is covered by the refrigerator inspection service."},
            {"question": "Will repairs start immediately after inspection?", "answer": "The technician first explains the diagnosis and estimate; additional work proceeds only after approval."},
        ],
    },
)


def seed_pages(apps, schema_editor):
    SeoLandingPage = apps.get_model("catalogue", "SeoLandingPage")
    for page in PAGES:
        page_slug = "/".join(part for part in (page["service_slug"], page["area_slug"]) if part)
        SeoLandingPage.objects.update_or_create(
            service_slug=page["service_slug"],
            area_slug=page["area_slug"],
            defaults={**page, "page_slug": page_slug, "city": "Chennai", "is_active": True, "is_indexable": True},
        )


def remove_pages(apps, schema_editor):
    SeoLandingPage = apps.get_model("catalogue", "SeoLandingPage")
    keys = [(page["service_slug"], page["area_slug"]) for page in PAGES]
    for service_slug, area_slug in keys:
        SeoLandingPage.objects.filter(service_slug=service_slug, area_slug=area_slug).delete()


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0010_seolandingpage")]

    operations = [migrations.RunPython(seed_pages, remove_pages)]
