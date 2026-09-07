import re

# Common countries + major tech hub cities — extend as needed
KNOWN_LOCATIONS = [
    "india", "united states", "usa", "us", "uk", "united kingdom", "canada",
    "germany", "france", "singapore", "australia", "japan", "netherlands",
    "ireland", "spain", "italy", "poland", "mexico", "brazil", "remote",
    "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad", "pune", "chennai",
    "new york", "san francisco", "seattle", "austin", "chicago", "boston",
    "london", "berlin", "paris", "toronto", "vancouver", "sydney", "melbourne",
    "dublin", "amsterdam", "tokyo", "singapore city",
]

# sorted longest-first so multi-word locations match before their substrings
_SORTED_LOCATIONS = sorted(KNOWN_LOCATIONS, key=len, reverse=True)


def location_matches_strict(job_location: str | None, target: str) -> bool:
    """Strict: excludes jobs with missing/unmatched location. No pass-through for unknowns."""
    if not job_location:
        return False
    return target.lower() in job_location.lower()