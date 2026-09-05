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


def location_matches(job_location: str | None, target: str) -> bool:
    """True if job_location contains target, or job_location is missing (pass-through)."""
    if not job_location:
        return True  # unknown location — don't exclude, just can't confirm match
    return target.lower() in job_location.lower()