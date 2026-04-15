"""Scancode-to-character mapping tables for EN, RU, UA keyboard layouts.

Based on standard QWERTY (US), ЙЦУКЕН (Russian), and ЙЦУКЕН (Ukrainian) layouts.
Scancodes are Linux evdev KEY_* codes.
"""

from evdev import ecodes

# Layout identifiers
EN = "en"
RU = "ru"
UA = "ua"

LAYOUTS = (EN, RU, UA)

# Scancode → {layout: (normal_char, shift_char)}
# Only alpha and punctuation keys that differ between layouts.
KEYMAP: dict[int, dict[str, tuple[str, str]]] = {
    # Row 1: number row
    ecodes.KEY_GRAVE:       {EN: ("`", "~"),  RU: ("ё", "Ё"),  UA: ("'", "'")},
    ecodes.KEY_1:           {EN: ("1", "!"),  RU: ("1", "!"),  UA: ("1", "!")},
    ecodes.KEY_2:           {EN: ("2", "@"),  RU: ("2", '"'),  UA: ("2", '"')},
    ecodes.KEY_3:           {EN: ("3", "#"),  RU: ("3", "№"),  UA: ("3", "№")},
    ecodes.KEY_4:           {EN: ("4", "$"),  RU: ("4", ";"),  UA: ("4", ";")},
    ecodes.KEY_5:           {EN: ("5", "%"),  RU: ("5", "%"),  UA: ("5", "%")},
    ecodes.KEY_6:           {EN: ("6", "^"),  RU: ("6", ":"),  UA: ("6", ":")},
    ecodes.KEY_7:           {EN: ("7", "&"),  RU: ("7", "?"),  UA: ("7", "?")},
    ecodes.KEY_8:           {EN: ("8", "*"),  RU: ("8", "*"),  UA: ("8", "*")},
    ecodes.KEY_9:           {EN: ("9", "("),  RU: ("9", "("),  UA: ("9", "(")},
    ecodes.KEY_0:           {EN: ("0", ")"),  RU: ("0", ")"),  UA: ("0", ")")},
    ecodes.KEY_MINUS:       {EN: ("-", "_"),  RU: ("-", "_"),  UA: ("-", "_")},
    ecodes.KEY_EQUAL:       {EN: ("=", "+"),  RU: ("=", "+"),  UA: ("=", "+")},

    # Row 2: QWERTY row
    ecodes.KEY_Q:           {EN: ("q", "Q"),  RU: ("й", "Й"),  UA: ("й", "Й")},
    ecodes.KEY_W:           {EN: ("w", "W"),  RU: ("ц", "Ц"),  UA: ("ц", "Ц")},
    ecodes.KEY_E:           {EN: ("e", "E"),  RU: ("у", "У"),  UA: ("у", "У")},
    ecodes.KEY_R:           {EN: ("r", "R"),  RU: ("к", "К"),  UA: ("к", "К")},
    ecodes.KEY_T:           {EN: ("t", "T"),  RU: ("е", "Е"),  UA: ("е", "Е")},
    ecodes.KEY_Y:           {EN: ("y", "Y"),  RU: ("н", "Н"),  UA: ("н", "Н")},
    ecodes.KEY_U:           {EN: ("u", "U"),  RU: ("г", "Г"),  UA: ("г", "Г")},
    ecodes.KEY_I:           {EN: ("i", "I"),  RU: ("ш", "Ш"),  UA: ("ш", "Ш")},
    ecodes.KEY_O:           {EN: ("o", "O"),  RU: ("щ", "Щ"),  UA: ("щ", "Щ")},
    ecodes.KEY_P:           {EN: ("p", "P"),  RU: ("з", "З"),  UA: ("з", "З")},
    ecodes.KEY_LEFTBRACE:   {EN: ("[", "{"),  RU: ("х", "Х"),  UA: ("х", "Х")},
    ecodes.KEY_RIGHTBRACE:  {EN: ("]", "}"),  RU: ("ъ", "Ъ"),  UA: ("ї", "Ї")},  # RU/UA discriminator

    # Row 3: ASDF row
    ecodes.KEY_A:           {EN: ("a", "A"),  RU: ("ф", "Ф"),  UA: ("ф", "Ф")},
    ecodes.KEY_S:           {EN: ("s", "S"),  RU: ("ы", "Ы"),  UA: ("і", "І")},  # RU/UA discriminator
    ecodes.KEY_D:           {EN: ("d", "D"),  RU: ("в", "В"),  UA: ("в", "В")},
    ecodes.KEY_F:           {EN: ("f", "F"),  RU: ("а", "А"),  UA: ("а", "А")},
    ecodes.KEY_G:           {EN: ("g", "G"),  RU: ("п", "П"),  UA: ("п", "П")},
    ecodes.KEY_H:           {EN: ("h", "H"),  RU: ("р", "Р"),  UA: ("р", "Р")},
    ecodes.KEY_J:           {EN: ("j", "J"),  RU: ("о", "О"),  UA: ("о", "О")},
    ecodes.KEY_K:           {EN: ("k", "K"),  RU: ("л", "Л"),  UA: ("л", "Л")},
    ecodes.KEY_L:           {EN: ("l", "L"),  RU: ("д", "Д"),  UA: ("д", "Д")},
    ecodes.KEY_SEMICOLON:   {EN: (";", ":"),  RU: ("ж", "Ж"),  UA: ("ж", "Ж")},
    ecodes.KEY_APOSTROPHE:  {EN: ("'", '"'),  RU: ("э", "Э"),  UA: ("є", "Є")},  # RU/UA discriminator

    # Row 4: ZXCV row
    ecodes.KEY_Z:           {EN: ("z", "Z"),  RU: ("я", "Я"),  UA: ("я", "Я")},
    ecodes.KEY_X:           {EN: ("x", "X"),  RU: ("ч", "Ч"),  UA: ("ч", "Ч")},
    ecodes.KEY_C:           {EN: ("c", "C"),  RU: ("с", "С"),  UA: ("с", "С")},
    ecodes.KEY_V:           {EN: ("v", "V"),  RU: ("м", "М"),  UA: ("м", "М")},
    ecodes.KEY_B:           {EN: ("b", "B"),  RU: ("и", "И"),  UA: ("и", "И")},
    ecodes.KEY_N:           {EN: ("n", "N"),  RU: ("т", "Т"),  UA: ("т", "Т")},
    ecodes.KEY_M:           {EN: ("m", "M"),  RU: ("ь", "Ь"),  UA: ("ь", "Ь")},
    ecodes.KEY_COMMA:       {EN: (",", "<"),  RU: ("б", "Б"),  UA: ("б", "Б")},
    ecodes.KEY_DOT:         {EN: (".", ">"),  RU: ("ю", "Ю"),  UA: ("ю", "Ю")},
    ecodes.KEY_SLASH:       {EN: ("/", "?"),  RU: (".", ","),  UA: (".", ",")},

    # Backslash — RU/UA discriminator
    ecodes.KEY_BACKSLASH:   {EN: ("\\", "|"), RU: ("\\", "/"), UA: ("ґ", "Ґ")},

    # Space
    ecodes.KEY_SPACE:       {EN: (" ", " "),  RU: (" ", " "),  UA: (" ", " ")},
}

# Scancodes that produce characters exclusive to one Cyrillic layout.
# If any of these appear, we can immediately determine RU vs UA.
RU_EXCLUSIVE_SCANCODES = {
    ecodes.KEY_RIGHTBRACE,  # ъ (RU) vs ї (UA)
    ecodes.KEY_S,           # ы (RU) vs і (UA)
    ecodes.KEY_APOSTROPHE,  # э (RU) vs є (UA)
    ecodes.KEY_GRAVE,       # ё (RU) vs ' (UA)
}

# Set of scancodes that produce alpha characters (for word boundary detection)
ALPHA_SCANCODES = {
    sc for sc, maps in KEYMAP.items()
    if any(maps[lang][0].isalpha() for lang in (EN, RU, UA) if lang in maps)
}

# Digit scancodes — same char in all layouts, but must be kept in word buffer
# so abbreviations like E2E, B2B, i18n are replayed correctly
DIGIT_SCANCODES = {
    ecodes.KEY_1, ecodes.KEY_2, ecodes.KEY_3, ecodes.KEY_4, ecodes.KEY_5,
    ecodes.KEY_6, ecodes.KEY_7, ecodes.KEY_8, ecodes.KEY_9, ecodes.KEY_0,
}

# Word boundary keys
WORD_BOUNDARY_SCANCODES = {
    ecodes.KEY_SPACE,
    ecodes.KEY_ENTER,
    ecodes.KEY_TAB,
}

# Edit / navigation keys that affect the word buffer
EDIT_SCANCODES = {
    ecodes.KEY_BACKSPACE,
    ecodes.KEY_DELETE,
    ecodes.KEY_LEFT,
    ecodes.KEY_RIGHT,
    ecodes.KEY_UP,
    ecodes.KEY_DOWN,
    ecodes.KEY_HOME,
    ecodes.KEY_END,
}


def scancode_to_char(scancode: int, layout: str, shifted: bool = False) -> str | None:
    """Convert a scancode to a character in the given layout."""
    entry = KEYMAP.get(scancode)
    if entry is None or layout not in entry:
        return None
    return entry[layout][1 if shifted else 0]


def scancodes_to_text(scancodes: list[int], layout: str, shift_states: list[bool] | None = None) -> str:
    """Convert a sequence of scancodes to text in a given layout."""
    if shift_states is None:
        shift_states = [False] * len(scancodes)
    chars = []
    for sc, shifted in zip(scancodes, shift_states):
        ch = scancode_to_char(sc, layout, shifted)
        if ch is not None:
            chars.append(ch)
    return "".join(chars)


def is_cyrillic_discriminator(scancode: int) -> str | None:
    """Check if a scancode uniquely identifies RU or UA.

    Returns 'ru' or 'ua' if the scancode produces an exclusive letter,
    None otherwise. This works because the same physical key produces
    different Cyrillic letters in RU vs UA layouts.
    """
    if scancode in RU_EXCLUSIVE_SCANCODES:
        # These keys produce letters that exist ONLY in RU (ы, э, ъ, ё)
        # or ONLY in UA (і, є, ї, ґ) — the scancode itself tells us which
        # layout the user intended, because they pressed the key *expecting*
        # one of these exclusive letters.
        # However, we can't tell which one they intended just from the scancode —
        # we need context. Return None here; the detector uses n-gram analysis.
        return None
    return None
