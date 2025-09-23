import re
import datetime

_UNIT_MAP = {
    'kg': {'kg', 'kgs', 'kilo', 'kilos', 'kilogram', 'kilograms'},
    'g': {'g', 'gram', 'grams'},
    # liters: include many common misspellings/abbreviations
    'l': {'l', 'lt', 'ltr', 'ltrs', 'liter', 'litre', 'liters', 'litres', 'litr', 'ltl'},
    'ml': {'ml', 'milliliter', 'millilitre', 'milliliters', 'millilitres', 'milli', 'mltr', 'mltrs'},
    'pieces': {'pcs', 'piece', 'pieces', 'pc'},
    'packet': {'packet', 'packets', 'pkt', 'pkts'},
    'bottle': {'bottle', 'bottles'},
    'box': {'box', 'boxes'},
    'case': {'case', 'cases'},
    'crate': {'crate', 'crates'},
    'bag': {'bag', 'bags'},
    'carton': {'carton', 'cartons'},
    'roll': {'roll', 'rolls'},
    'dozen': {'dozen', 'dozens', 'dz'},
}


def _fmt_timestamp() -> str:
    """Return timestamp like '16 sep 2025 14:05:33' (24h, month lower)."""
    try:
        return datetime.datetime.now().strftime('%d %b %Y %H:%M:%S').lower()
    except Exception:
        return datetime.datetime.now().isoformat(timespec='seconds')


def _normalize_unit(unit: str) -> str:
    import re
    u = (unit or '').strip().lower()
    # strip punctuation commonly attached to abbreviations (e.g., "lt.")
    u = u.replace('.', '')
    # collapse spaces and hyphens
    u = u.replace('-', '').replace(' ', '')
    if not u:
        return ''
    for std, aliases in _UNIT_MAP.items():
        if u in aliases:
            return std
    # simple singularization heuristics if not in map
    cand = None
    if u.endswith('ies') and len(u) > 3:
        cand = u[:-3] + 'y'
    elif u.endswith('es') and len(u) > 2:
        cand = u[:-2]
    elif u.endswith('s') and len(u) > 1:
        cand = u[:-1]
    if cand:
        for std, aliases in _UNIT_MAP.items():
            if cand in aliases or cand == std:
                return std
        return cand
    return u


def _clean_item(item: str) -> str:
    s = (item or '').strip()
    # Drop leading fillers like 'of ', 'the ', 'a ', 'an '
    for prefix in ('of ', 'the ', 'a ', 'an '):
        if s.lower().startswith(prefix):
            s = s[len(prefix):].strip()
    return s


def _split_location(phrase: str):
    text = phrase.strip()
    for sep in (" to ", " from ", " in "):
        pos = text.lower().find(sep)
        if pos != -1:
            return text[:pos].strip(), text[pos + len(sep):].strip()
    lower = text.lower()
    for sep in ("to ", "from ", "in "):
        if lower.startswith(sep):
            return '', text[len(sep):].strip()
    return text, ''


def parse_inventory_command(text: str) -> dict | None:
    """Parse commands like 'add 5kgs of onions in pantry' or 'remove onions 2 kg'.

    Returns a dict with keys: timestamp, action, item, quantity, unit, location, note.
    Returns None when not understood.
    """
    s = (text or '').strip()
    if not s:
        return None
    low = s.lower()
    action = None
    # Treat synonyms of removal as the same action
    REMOVE_WORDS = ("remove", "deduct", "subtract", "reduce", "delete")
    for kw in ("add",) + REMOVE_WORDS:
        if low.startswith(kw + ' ') or (' ' + kw + ' ') in (' ' + low + ' '):
            action = 'add' if kw == 'add' else 'remove'
            break
    if not action:
        return None

    # Remove action from the start if present
    rest = low
    if rest.startswith('add '):
        rest = rest[4:]
    elif rest.startswith('remove '):
        rest = rest[7:]
    elif rest.startswith('deduct '):
        rest = rest[7:]
    elif rest.startswith('subtract '):
        rest = rest[9:]
    elif rest.startswith('reduce '):
        rest = rest[7:]
    elif rest.startswith('delete '):
        rest = rest[7:]

    # Pattern A: qty first -> "5 kg of onions" / "5kgs onions"
    m = re.match(r"^\s*(\d+(?:[\.,]\d+)?)\s*([a-zA-Z]+)?(?:\s+of)?\s+(.+)$", rest)
    qty = None
    unit = ''
    item = ''
    loc = ''
    if m:
        try:
            qty = float(m.group(1).replace(',', '.'))
        except Exception:
            qty = None
        unit = _normalize_unit(m.group(2) or '')
        item_part = m.group(3)
        item_part, loc = _split_location(item_part)
        item = _clean_item(item_part)
    else:
        # Pattern B: item first -> "onions 5 kg" or "onions 5kg in pantry"
        m2 = re.match(r"^\s*(.+?)\s+(\d+(?:[\.,]\d+)?)\s*([a-zA-Z]+)?(.*)$", rest)
        if m2:
            item_part = m2.group(1)
            try:
                qty = float(m2.group(2).replace(',', '.'))
            except Exception:
                qty = None
            unit = _normalize_unit(m2.group(3) or '')
            tail = (m2.group(4) or '')
            # tail may include location like ' in pantry'
            _, loc = _split_location(tail)
            item = _clean_item(item_part)
        else:
            # Fallback: previous heuristic -- after removing qty/unit
            m3 = re.search(r"(\d+(?:[\.,]\d+)?)\s*([a-zA-Z]+)?", rest)
            if m3:
                try:
                    qty = float(m3.group(1).replace(',', '.'))
                except Exception:
                    qty = None
                unit = _normalize_unit(m3.group(2) or '')
                after = rest.split(m3.group(0), 1)[1].strip()
                after, loc = _split_location(after)
                item = _clean_item(after)
            else:
                # No quantity found, treat all as item
                item, loc = _split_location(rest)
                item = _clean_item(item)

    if not item:
        return None
    return {
        'timestamp': _fmt_timestamp(),
        'action': action,
        'item': item,
        'quantity': qty if qty is not None else '',
        'unit': unit,
        'location': loc,
        'note': '',
    }
