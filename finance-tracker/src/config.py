import os
from pathlib import Path


MY_CATEGORIES = {
    "Groceries": [
        "FOOD_AND_DRINK_GROCERIES",
    ],
    "Eating out": [
        "FOOD_AND_DRINK_RESTAURANT",
        "FOOD_AND_DRINK_RESTAURANTS",
        "FOOD_AND_DRINK_COFFEE",
        "FOOD_AND_DRINK_FAST_FOOD",
        "FOOD_AND_DRINK_BEER_WINE_AND_LIQUOR",
        "FOOD_AND_DRINK_VENDING_MACHINES",
        "FOOD_AND_DRINK_OTHER_FOOD_AND_DRINK",
    ],
    "Transport": [
        "TRANSPORTATION_GAS",
        "TRANSPORTATION_PUBLIC_TRANSIT",
        "TRANSPORTATION_TAXIS_AND_RIDE_SHARES",
        "TRANSPORTATION_PARKING",
        "TRANSPORTATION_TOLLS",
        "TRANSPORTATION_BIKES_AND_SCOOTERS",
        "TRANSPORTATION_OTHER_TRANSPORTATION",
    ],
    "Housing": [
        "RENT_AND_UTILITIES_RENT",
        "RENT_AND_UTILITIES_GAS_AND_ELECTRICITY",
        "RENT_AND_UTILITIES_WATER",
        "RENT_AND_UTILITIES_SEWAGE_AND_WASTE_MANAGEMENT",
        "RENT_AND_UTILITIES_TELEPHONE",
        "RENT_AND_UTILITIES_INTERNET_AND_CABLE",
        "RENT_AND_UTILITIES_OTHER_UTILITIES",
        "HOME_IMPROVEMENT_HARDWARE",
        "HOME_IMPROVEMENT_REPAIR_AND_MAINTENANCE",
        "HOME_IMPROVEMENT_FURNITURE",
        "HOME_IMPROVEMENT_OTHER_HOME_IMPROVEMENT",
    ],
    "Subscriptions": [
        "ENTERTAINMENT_TV_AND_MOVIES",
        "ENTERTAINMENT_MUSIC_AND_AUDIO",
        "ENTERTAINMENT_VIDEO_GAMES",
    ],
    "Shopping": [
        "GENERAL_MERCHANDISE_CLOTHING_AND_ACCESSORIES",
        "GENERAL_MERCHANDISE_ELECTRONICS",
        "GENERAL_MERCHANDISE_DEPARTMENT_STORES",
        "GENERAL_MERCHANDISE_DISCOUNT_STORES",
        "GENERAL_MERCHANDISE_ONLINE_MARKETPLACES",
        "GENERAL_MERCHANDISE_SUPERSTORES",
        "GENERAL_MERCHANDISE_BOOKSTORES_AND_NEWSSTANDS",
        "GENERAL_MERCHANDISE_CONVENIENCE_STORES",
        "GENERAL_MERCHANDISE_GIFTS_AND_NOVELTIES",
        "GENERAL_MERCHANDISE_OFFICE_SUPPLIES",
        "GENERAL_MERCHANDISE_PET_SUPPLIES",
        "GENERAL_MERCHANDISE_SPORTING_GOODS",
        "GENERAL_MERCHANDISE_TOBACCO_AND_VAPE",
        "GENERAL_MERCHANDISE_OTHER_GENERAL_MERCHANDISE",
    ],
    "Healthcare": [
        "MEDICAL_DENTAL_CARE",
        "MEDICAL_EYE_CARE",
        "MEDICAL_NURSING_CARE",
        "MEDICAL_PHARMACIES_AND_SUPPLEMENTS",
        "MEDICAL_PRIMARY_CARE",
        "MEDICAL_VETERINARY_SERVICES",
        "MEDICAL_OTHER_MEDICAL",
    ],
    "Travel": [
        "TRAVEL_FLIGHTS",
        "TRAVEL_LODGING",
        "TRAVEL_RENTAL_CARS",
        "TRAVEL_GAS",
        "TRAVEL_PUBLIC_TRANSIT",
        "TRAVEL_TAXIS_AND_RIDE_SHARES",
        "TRAVEL_OTHER_TRAVEL",
    ],
    "Other": [],
}


_REVERSE = {plaid_cat: bucket for bucket, plaid_cats in MY_CATEGORIES.items() for plaid_cat in plaid_cats}


def remap_category(primary):
    if primary is None:
        return "Other"
    return _REVERSE.get(primary, "Other")


_PLAID_HOSTS = {
    "sandbox": "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production": "https://production.plaid.com",
}


def plaid_host(env=None):
    env = (env or os.getenv("PLAID_ENV") or "sandbox").lower()
    if env not in _PLAID_HOSTS:
        raise ValueError(f"Unknown PLAID_ENV: {env!r}")
    return _PLAID_HOSTS[env]


def data_dir():
    override = os.getenv("FINANCE_DATA_DIR")
    if override:
        path = Path(override)
    else:
        path = Path(__file__).resolve().parent.parent / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path():
    return data_dir() / "finance.db"


def tokens_path():
    return data_dir() / "tokens.enc"


INSTITUTIONS = ["chase", "capital_one", "discover", "schwab", "bask"]

REQUIRED_ENV_VARS = ("PLAID_CLIENT_ID", "PLAID_SECRET", "PLAID_ENV", "GSHEET_ID", "FERNET_KEY")


def require_env():
    missing = [v for v in REQUIRED_ENV_VARS if not os.getenv(v)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
    return {v: os.getenv(v) for v in REQUIRED_ENV_VARS}


require_env()

PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID", "")
PLAID_SECRET = os.getenv("PLAID_SECRET", "")
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")
GSHEET_ID = os.getenv("GSHEET_ID", "")
FERNET_KEY = os.getenv("FERNET_KEY", "")
