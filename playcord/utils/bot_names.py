import random

BOT_FIRST_NAMES = [
    "Mary",
    "Alex",
    "Sam",
    "Jordan",
    "Taylor",
    "Avery",
    "Riley",
    "Casey",
    "Morgan",
    "Jamie",
    "Quinn",
    "Harper",
    "Skyler",
    "Parker",
    "Reese",
    "Rowan",
]


def generate_bot_name(used_names: set[str] | None = None) -> str:
    """
    Generate a unique display name for a bot in the form "<Name> (Bot)".
    """
    used_names = used_names or set()
    shuffled = BOT_FIRST_NAMES[:]
    random.shuffle(shuffled)
    for first_name in shuffled:
        candidate = f"{first_name} (Bot)"
        if candidate not in used_names:
            return candidate
    suffix = random.randint(100, 999)
    return f"Bot {suffix} (Bot)"
