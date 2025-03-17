# This allows importing from RW2 source code files, such as Level
import sys
sys.path.append('../..')

import Level
from Level import Spell, Buff

# This retrieves the main module; not sure why import RiftWizard2 doesn't work
import inspect
frm = inspect.stack()[-1]
RiftWizard2 = inspect.getmodule(frm[0])

import os

import urllib.request, json
from functools import cmp_to_key, lru_cache
import threading

# -------------------- lib
# not sure how to move this into another file; imports fail if it's not here and other mods I've seen
# are also only single files.

# remove_suffix removes suffix from text if it is present. This is in the stdlib in Python3.9, but the
# game runs 3.8.
def remove_suffix(text, suffix):
    if suffix and text.endswith(suffix):
        return text[:-len(suffix)]
    return text

# hook_attr replaces an attribute of an object with a different value.
def hook_attr(target_obj, attribute, replacement):
    orig = getattr(target_obj, attribute)

    setattr(target_obj, attribute, replacement)

    return lambda: setattr(target_obj, attribute, orig)

# hook_func replaces the function named by hook_func of an object with hook_func.
# hook_func receives the original function, plus all args passed to the original function.
def hook_func(target_obj, hook_func):
    attribute = remove_suffix(hook_func.__name__, "_hook")

    orig = getattr(target_obj, attribute)

    def new_func(*args, **kwargs):
        return hook_func(orig, *args, **kwargs)

    setattr(target_obj, attribute, new_func)

    return lambda: setattr(target_obj, attribute, orig)

# hook is the decorator version of hook_func. It does not allow unhooking.
def hook(*target_objs):
    def inner(hook):
        for target_obj in target_objs:
            hook_func(target_obj, hook)
        return hook
    return inner

# HookAttr is the Context manager variant of hook_attr. It automatically unhooks when the context ends.
class HookAttr():
    def __init__(self, target_obj, target_attr, hook_attr):
        self.target_obj = target_obj
        self.target_attr = target_attr
        self.hook_attr = hook_attr
        self.unhook = None

    def __enter__(self):
        self.unhook = hook_attr(self.target_obj, self.target_attr, self.hook_attr)

    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.unhook()

# Hook is the Context manager variant of hook_func. It automatically unhooks when the context ends.
class Hook():
    def __init__(self, target_obj, hook_func):
        self.target_obj = target_obj
        self.hook_func = hook_func
        self.unhook = None

    def __enter__(self):
        self.unhook = hook_func(self.target_obj, self.hook_func)

    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.unhook()

# Notifier wraps an object and transparently passes through all attribute access on it to the wrapped object.
# When any access happens, it invokes a notification function with the accessed attribute.
class Notifier:
    def __init__(self, wrapped, notify):
        self.__wrapped = wrapped
        self.__notify = notify

    def __getattr__(self, name):
        self.__notify(name)
        return getattr(self.__wrapped, name)

# notify_once calls a notification function the first time obj.attribute is used.
def notify_once(obj, attribute, notify):
    orig = getattr(obj, attribute)

    def notify_hook(name):
        setattr(obj, attribute, orig)
        notify()

    # Move wrap and unwrap to notifier?
    setattr(obj, attribute, Notifier(orig, notify_hook))

# check_for_update checks whether an update has been released for this mod.
def check_for_update(name, current_version):
    def cmp(v1, v2):
        p1 = v1.split(".")
        p2 = v2.split(".")

        for i in range(3):
            i1, i2 = int(p1[i]), int(p2[i])

            if i1 != i2:
                return i1 - i2

        return 0

    if current_version == "?":
        return

    try: url = f"https://codeberg.org/api/v1/repos/danvolchek/rift-wizard-2-mods/releases?draft=false&pre-release=false&q={name}"

        req = urllib.request.Request(url=url, headers = {'accept': 'application/json'}, method="GET")
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
            releases = [{"version": release["name"].split()[1], "url": release["html_url"]} for release in data]
            releases.sort(key=cmp_to_key(lambda a, b: cmp(a["version"], b["version"])), reverse=True)

            latest = releases[0]

            if cmp(latest["version"], current_version) > 0:
                print(f"New version available: {name} v{latest['version']} ({latest['url']})")

    except Exception as e:
        pass

# -------------------- lib

# -------------------- hooks

# This would be a dataclass but the dataclass import fails for a reason I don't understand
class MessageSearchData:
    def __init__(self):
        # Text currently entered in the message filter
        self.filter_text = ""

        # Whether text is being entered in the message filter or not
        self.editing_filter_text = False

@hook(RiftWizard2.PyGameView)
def process_combat_log_input_hook(process_combat_log_input, self):
    page_size = self.middle_menu_display.get_height() // self.linesize - 1

    for evt in [e for e in self.events if e.type == pygame.KEYDOWN]:
        if evt.key in self.key_binds[KEY_BIND_PREV_EXAMINE_TARGET]:
            self.combat_log_scroll(-page_size)
        if evt.key in self.key_binds[KEY_BIND_NEXT_EXAMINE_TARGET]:
            self.combat_log_scroll(page_size)

    process_combat_log_input(self)

@hook(RiftWizard2.PyGameView)
def run_hook(run, self):
    if not hasattr(self, "_MessageSearchModData"):
        self._MessageSearchModData = MessageSearchData()

    run(self)

# -------------------- hooks

VERSION = "?"
CHECK_FOR_UPDATES = False

try:
    with open(os.path.join("mods", "MessageSearch", "version.txt")) as f:
        VERSION = f.read()
except:
    pass

print(f"Loaded MessageSearch mod v{VERSION} by Malex")

if CHECK_FOR_UPDATES:
    threading.Thread(target=check_for_update, args=("MessageSearch",VERSION)).start()
