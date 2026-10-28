"""Stable colors for POS cards."""
import hashlib

COLORS = [
    "#D84315",  # Deep Orange
    "#1565C0",  # Indigo Blue
    "#C2185B",  # Raspberry
    "#7B1FA2",  # Purple
    "#512DA8",  # Deep Purple
    "#9E9D24",  # Olive
    "#8D6E63",  # Brown
    "#5E35B1",  # Muted Violet
    "#2E7D32",  # Dark Green
]



def get_color_from_name(name: str) -> str:
    h = int(hashlib.md5(name.encode()).hexdigest(), 16)
    return COLORS[h % len(COLORS)]
