from . import imessage, google_messages, discord, signal_, whatsapp, snapchat, generic

EXTRACTORS = {
    'iMessage': imessage,
    'Google Messages': google_messages,
    'Discord': discord,
    'Signal': signal_,
    'WhatsApp': whatsapp,
    'Snapchat': snapchat,
    'Generic Import': generic,
}

def list_available():
    available = []
    for name, mod in EXTRACTORS.items():
        info = {'name': name, 'available': False, 'description': '', 'platforms': []}
        if hasattr(mod, 'is_available'):
            info['available'] = mod.is_available()
        if hasattr(mod, 'description'):
            info['description'] = getattr(mod, 'description', '')
        if hasattr(mod, 'platforms'):
            info['platforms'] = getattr(mod, 'platforms', [])
        info['has_extract'] = hasattr(mod, 'extract')
        info['has_import_file'] = hasattr(mod, 'import_file')
        available.append(info)
    return available

def extract_from(source_name, **kwargs):
    mod = EXTRACTORS.get(source_name)
    if mod is None:
        raise ValueError(f"Unknown source: {source_name}. Available: {list(EXTRACTORS.keys())}")
    if not hasattr(mod, 'extract'):
        raise NotImplementedError(f"{source_name} does not support direct extraction")
    return mod.extract(**kwargs)

def import_file(source_name, filepath, **kwargs):
    mod = EXTRACTORS.get(source_name)
    if mod is None:
        raise ValueError(f"Unknown source: {source_name}")
    if not hasattr(mod, 'import_file'):
        raise NotImplementedError(f"{source_name} does not support file import")
    return mod.import_file(filepath, **kwargs)

def extract_all(**kwargs):
    all_messages = []
    results = {}
    for name, mod in EXTRACTORS.items():
        if hasattr(mod, 'extract'):
            try:
                msgs = mod.extract(**kwargs)
                if msgs:
                    all_messages.extend(msgs)
                    results[name] = len(msgs)
            except Exception as e:
                results[name] = f"error: {e}"
        elif hasattr(mod, 'is_available') and mod.is_available():
            results[name] = "skipped (no direct extract)"
    return all_messages, results
