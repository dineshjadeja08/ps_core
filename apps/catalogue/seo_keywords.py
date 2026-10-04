LOCAL_TRANSACTIONAL_INTENT = "Local transactional service booking"


KEYWORD_CLUSTERS = {
    "ac-service-chennai": {
        "primary": "AC service in {area}",
        "secondary": (
            "AC repair in {area}", "AC cleaning in {area}", "AC gas refill in {area}",
            "AC installation in {area}", "AC uninstallation in {area}", "AC technician in {area}",
            "AC maintenance in {area}", "AC inspection in {area}",
        ),
        "supporting": ("doorstep AC service", "AC cooling diagnosis", "transparent service pricing"),
    },
    "washing-machine-repair-chennai": {
        "primary": "Washing machine repair in {area}",
        "secondary": (
            "Washing machine service in {area}", "Front load washing machine repair in {area}",
            "Top load washing machine repair in {area}", "Washing machine installation in {area}",
            "Washing machine technician in {area}", "Washing machine maintenance in {area}",
        ),
        "supporting": ("washing and spinning issues", "drainage diagnosis", "doorstep appliance inspection"),
    },
    "refrigerator-repair-chennai": {
        "primary": "Refrigerator repair in {area}",
        "secondary": (
            "Fridge repair in {area}", "Refrigerator service in {area}",
            "Fridge not cooling repair in {area}", "Refrigerator technician in {area}",
            "Refrigerator maintenance in {area}",
        ),
        "supporting": ("refrigerator cooling diagnosis", "fridge leakage inspection", "repair estimate"),
    },
    "tv-repair-chennai": {
        "primary": "TV repair in {area}",
        "secondary": (
            "LED TV repair in {area}", "LCD TV repair in {area}", "Smart TV repair in {area}",
            "TV technician in {area}", "Television service in {area}",
        ),
        "supporting": ("television fault diagnosis", "display issue inspection", "doorstep TV service"),
    },
    "water-purifier-service-chennai": {
        "primary": "Water purifier service in {area}",
        "secondary": (
            "RO service in {area}", "RO repair in {area}", "Water purifier repair in {area}",
            "Water purifier installation in {area}", "RO technician in {area}",
            "Water purifier maintenance in {area}",
        ),
        "supporting": ("RO and UV purifier inspection", "filter replacement estimate", "water flow diagnosis"),
    },
    "geyser-repair-chennai": {
        "primary": "Geyser repair in {area}",
        "secondary": (
            "Geyser service in {area}", "Water heater repair in {area}", "Geyser installation in {area}",
            "Electric geyser repair in {area}", "Geyser maintenance in {area}",
        ),
        "supporting": ("water heater diagnosis", "geyser leakage inspection", "heating issue service"),
    },
    "tv-wall-mount-installation-chennai": {
        "primary": "TV wall mount installation in {area}",
        "secondary": (
            "TV mounting service in {area}", "LED TV wall mounting in {area}",
            "TV bracket installation in {area}",
        ),
        "supporting": ("TV bracket fitting", "wall mounting assessment", "television installation"),
    },
    "cctv-installation-chennai": {
        "primary": "CCTV installation in {area}",
        "secondary": (
            "CCTV camera installation in {area}", "CCTV repair in {area}",
            "Security camera installation in {area}", "CCTV maintenance in {area}",
            "CCTV technician in {area}",
        ),
        "supporting": ("security camera setup", "CCTV fault diagnosis", "camera coverage assessment"),
    },
    "dishwasher-repair-chennai": {
        "primary": "Dishwasher repair in {area}",
        "secondary": (
            "Dishwasher service in {area}", "Dishwasher installation in {area}",
            "Dishwasher technician in {area}", "Dishwasher maintenance in {area}",
        ),
        "supporting": ("dishwasher drainage diagnosis", "cleaning issue inspection", "appliance installation"),
    },
    "chimney-service-chennai": {
        "primary": "Chimney service in {area}",
        "secondary": (
            "Chimney cleaning in {area}", "Kitchen chimney repair in {area}",
            "Chimney installation in {area}", "Chimney deep cleaning in {area}",
        ),
        "supporting": ("kitchen chimney maintenance", "grease cleaning", "chimney inspection"),
    },
    "mosquito-net-installation-chennai": {
        "primary": "Mosquito net installation in {area}",
        "secondary": (
            "Window mosquito net in {area}", "Mosquito mesh installation in {area}",
            "Mosquito net repair in {area}", "Door mosquito mesh in {area}",
        ),
        "supporting": ("window mesh fitting", "door mosquito net", "mosquito screen measurement"),
    },
    "sofa-repair-chennai": {
        "primary": "Sofa repair in {area}",
        "secondary": (
            "Sofa upholstery in {area}", "Sofa reupholstery in {area}", "Couch repair in {area}",
            "Furniture upholstery in {area}",
        ),
        "supporting": ("sofa condition assessment", "upholstery options", "couch restoration"),
    },
    "water-tank-cleaning-chennai": {
        "primary": "Water tank cleaning in {area}",
        "secondary": (
            "Sump cleaning in {area}", "Overhead tank cleaning in {area}",
            "Underground sump cleaning in {area}", "Water tank cleaning service in {area}",
        ),
        "supporting": ("domestic tank cleaning", "sediment removal", "overhead and sump cleaning"),
    },
}


def keyword_targets(service_slug, location, service_name=""):
    cluster = KEYWORD_CLUSTERS.get(service_slug)
    if not cluster:
        return {
            "primary_keyword": f"{service_name} in {location}".strip(),
            "secondary_keywords": [],
            "supporting_terms": [],
            "search_intent": LOCAL_TRANSACTIONAL_INTENT,
        }
    return {
        "primary_keyword": cluster["primary"].format(area=location),
        "secondary_keywords": [value.format(area=location) for value in cluster["secondary"]],
        "supporting_terms": list(cluster["supporting"]),
        "search_intent": LOCAL_TRANSACTIONAL_INTENT,
    }
