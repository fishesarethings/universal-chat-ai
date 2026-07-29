import importlib

EXTRACTOR_NAMES = {
    'iMessage': 'imessage',
    'Google Messages': 'google_messages',
    'Discord': 'discord',
    'Signal': 'signal_',
    'WhatsApp': 'whatsapp',
    'Snapchat': 'snapchat',
    'Generic Import': 'generic',
    'iPhone (USB)': 'idevice',
    'Android (USB)': 'android',
}

DEVICE_EXTRACTORS = {
    'iPhone (USB)': 'idevice',
    'Android (USB)': 'android',
}

def _load(name):
    module_name = EXTRACTOR_NAMES.get(name)
    if not module_name:
        raise ValueError(f"Unknown extractor: {name}")
    return importlib.import_module(f'.{module_name}', __package__)

def list_available():
    available = []
    for name in EXTRACTOR_NAMES:
        info = {'name': name, 'available': False, 'description': '', 'platforms': [],
                'has_extract': False, 'has_import_file': False, 'is_device': name in DEVICE_EXTRACTORS}
        try:
            mod = _load(name)
            if hasattr(mod, 'is_available'):
                info['available'] = mod.is_available()
            if hasattr(mod, 'description'):
                info['description'] = getattr(mod, 'description', '')
            if hasattr(mod, 'platforms'):
                info['platforms'] = getattr(mod, 'platforms', [])
            info['has_extract'] = hasattr(mod, 'extract')
            info['has_import_file'] = hasattr(mod, 'import_file')
        except Exception as e:
            info['error'] = str(e)
        available.append(info)
    return available

def detect_devices():
    results = {}
    for name, module_name in DEVICE_EXTRACTORS.items():
        try:
            mod = _load(name)
            if hasattr(mod, 'detect_devices'):
                devices = mod.detect_devices()
                if devices:
                    results[name] = {'devices': devices, 'available_apps': []}
                    if hasattr(mod, 'get_available_apps') and devices:
                        results[name]['available_apps'] = mod.get_available_apps(devices[0]['udid'])
            elif hasattr(mod, 'is_available'):
                results[name] = {'available': mod.is_available()}
        except Exception as e:
            results[name] = {'error': str(e)}
    return results

def extract_from(source_name, **kwargs):
    mod = _load(source_name)
    if not hasattr(mod, 'extract'):
        raise NotImplementedError(f"{source_name} does not support direct extraction")
    return mod.extract(**kwargs)

def import_file(source_name, filepath, **kwargs):
    mod = _load(source_name)
    if not hasattr(mod, 'import_file'):
        raise NotImplementedError(f"{source_name} does not support file import")
    return mod.import_file(filepath, **kwargs)

def extract_all(**kwargs):
    all_messages = []
    results = {}
    for name in EXTRACTOR_NAMES:
        try:
            mod = _load(name)
            if hasattr(mod, 'extract'):
                msgs = mod.extract(**kwargs)
                if msgs:
                    all_messages.extend(msgs)
                    results[name] = len(msgs)
            elif hasattr(mod, 'is_available') and mod.is_available():
                results[name] = "skipped (no direct extract)"
        except Exception as e:
            results[name] = f"error: {e}"
    return all_messages, results