import os
import sys

import pygame

# This allows importing from RW2 source code files, such as Level
sys.path.append("../..")

# This retrieves the main module
import inspect

frm = inspect.stack()[-1]
RiftWizard2 = inspect.getmodule(frm[0])


# --------------------------------------------------------------------------------
# Lib code written by @danvolchek
# remove_suffix removes suffix from text if it is present. This is in the stdlib in Python3.9, but the
# game runs 3.8.
def remove_suffix(text, suffix):
    if suffix and text.endswith(suffix):
        return text[: -len(suffix)]
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
class HookAttr:
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
class Hook:
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


# End of lib code
# --------------------------------------------------------------------------------
# Code for the MessageSearch mod
class MessageSearchData:
    def __init__(self):
        # Text currently entered in the message filter
        self.filter_text = ""
        self.other_filters = {"wizard": False, "ally": False, "enemy": False}

        # Whether text is being entered in the message filter or not
        self.editing_filter_text = False


@hook(RiftWizard2.PyGameView)
def process_combat_log_input_hook(process_combat_log_input, self):
    mod_data = self._MessageSearchModData

    events_to_remove = []
    filter_changed = False

    for evt in [e for e in self.events if e.type == RiftWizard2.pygame.KEYDOWN]:
        if evt.key == RiftWizard2.pygame.K_SLASH:
            self.play_sound("menu_confirm")
            mod_data.editing_filter_text = not mod_data.editing_filter_text
            events_to_remove.append(evt)

        if mod_data.editing_filter_text:
            if evt.key in self.key_binds[RiftWizard2.KEY_BIND_ABORT]:
                mod_data.editing_filter_text = False
                mod_data.filter_text = ""
                filter_changed = True
                events_to_remove.append(evt)

            if evt.key in self.key_binds[RiftWizard2.KEY_BIND_CONFIRM]:
                mod_data.editing_filter_text = False
                self.play_sound("menu_confirm")
                events_to_remove.append(evt)

            if evt.key == RiftWizard2.pygame.K_BACKSPACE:
                if len(mod_data.filter_text) > 0:
                    mod_data.filter_text = mod_data.filter_text[:-1]
                    filter_changed = True
                else:
                    self.play_sound("hit_4")
                events_to_remove.append(evt)

            if (
                RiftWizard2.pygame.K_a <= evt.key <= RiftWizard2.pygame.K_z
                or evt.key == RiftWizard2.pygame.K_SPACE
            ):
                mod_data.filter_text += chr(evt.key)
                filter_changed = True
                events_to_remove.append(evt)
        else:
            if evt.key == pygame.K_r:
                mod_data.filter_text = ""
                mod_data.other_filters = {
                    "wizard": False,
                    "ally": False,
                    "enemy": False,
                }
                filter_changed = True
                events_to_remove.append(evt)
            if evt.key == pygame.K_w:
                mod_data.other_filters["wizard"] = not mod_data.other_filters["wizard"]
                filter_changed = True
                events_to_remove.append(evt)
            if evt.key == pygame.K_a:
                mod_data.other_filters["ally"] = not mod_data.other_filters["ally"]
                filter_changed = True
                events_to_remove.append(evt)
            if evt.key == pygame.K_e:
                mod_data.other_filters["enemy"] = not mod_data.other_filters["enemy"]
                filter_changed = True
                events_to_remove.append(evt)

        if filter_changed:
            self.play_sound("menu_confirm")
            self.set_combat_log_display(self.combat_log_level, self.combat_log_turn)

    self.events = [event for event in self.events if event not in events_to_remove]

    process_combat_log_input(self)


# Filter lines according to the text in the message filter
@hook(RiftWizard2.PyGameView)
def set_combat_log_display_hook(_set_combat_log_display, self, level, turn):
    mod_data = self._MessageSearchModData

    self.combat_log_level = level
    self.combat_log_turn = turn
    self.combat_log_lines = []

    log_fn = os.path.join(
        "saves",
        str(self.game.run_number),
        "log",
        str(level),
        "combat_log.%d.txt" % turn,
    )
    if os.path.exists(log_fn):
        with open(log_fn, "r") as logfile:
            self.combat_log_lines = [line.strip() for line in logfile.readlines()]

    first_line = self.combat_log_lines[0]
    if mod_data.filter_text:
        self.combat_log_lines = [
            line
            for line in self.combat_log_lines
            if mod_data.filter_text in line.lower() or line == first_line
        ]
    for filter_name, value in mod_data.other_filters.items():
        if value and filter_name in ["ally", "enemy"]:
            self.combat_log_lines = [
                line
                for line in self.combat_log_lines
                if ":%s" % filter_name in line or line == first_line
            ]
        elif value and filter_name == "wizard":
            self.combat_log_lines = [
                line
                for line in self.combat_log_lines
                if "Wizard" in line or line == first_line
            ]


# Show the message filter in the combat log
@hook(RiftWizard2.PyGameView)
def draw_combat_log_hook(draw_combat_log, self):
    mod_data = self._MessageSearchModData

    # During the draw_combat_log call, self.screen is called only once at the very end to transfer
    # the log lines to the screen.  This hook is called beforehand, during it the middle menu can be
    # drawn to before the final blit.
    def screen_used():
        cloud_frame_clock = RiftWizard2.cloud_frame_clock

        cur_x = 18 * 20
        cur_y = self.border_margin

        current_frame = cloud_frame_clock // RiftWizard2.STATUS_SUBFRAMES % 6
        color_frames = [(255, 213, 79), (255, 238, 88), (246, 254, 141)]

        self.draw_string("Filter by Text", self.middle_menu_display, cur_x, cur_y)
        cur_y += self.linesize

        color = color_frames[current_frame % 3]
        self.draw_string("/", self.middle_menu_display, cur_x, cur_y, color)

        if not mod_data.filter_text and not mod_data.editing_filter_text:
            color = (97, 97, 97)
        to_draw = mod_data.filter_text
        if mod_data.editing_filter_text:
            if current_frame % 2:
                to_draw += "_"
        else:
            to_draw = to_draw or "none"
        self.draw_string(
            to_draw,
            self.middle_menu_display,
            cur_x + self.font.size("/")[0],
            cur_y,
            color,
        )

        cur_x = 18 * 40
        cur_y = self.border_margin
        self.draw_string("Filters", self.middle_menu_display, cur_x, cur_y)

        cur_x += self.font.size("Filters")[0] + 36
        self.draw_string("Reset All", self.middle_menu_display, cur_x, cur_y)
        color = color_frames[current_frame % 3]
        self.draw_string("R", self.middle_menu_display, cur_x, cur_y, color)

        cur_x = 18 * 40
        cur_y += self.linesize
        for filter_name in ["Wizard", "Ally", "Enemy"]:
            self.draw_string(filter_name, self.middle_menu_display, cur_x, cur_y)
            if mod_data.other_filters[filter_name.lower()]:
                self.draw_string(
                    filter_name[1:],
                    self.middle_menu_display,
                    cur_x + self.font.size(filter_name[0])[0],
                    cur_y,
                    RiftWizard2.tooltip_colors[filter_name.lower()].to_tup(),
                )
            else:
                self.draw_string(
                    filter_name[0],
                    self.middle_menu_display,
                    cur_x,
                    cur_y,
                    RiftWizard2.tooltip_colors[filter_name.lower()].to_tup(),
                )
            cur_x += self.font.size(filter_name)[0] + 18

    notify_once(self, "screen", screen_used)
    draw_combat_log(self)


@hook(RiftWizard2.PyGameView)
def run_hook(run, self):
    if not hasattr(self, "_MessageSearchModData"):
        self._MessageSearchModData = MessageSearchData()

    run(self)


# Load the mod
VERSION = "?"

try:
    with open(os.path.join("mods", "MessageSearch", "version.txt")) as f:
        VERSION = f.read().strip()
except:
    pass

print(f"Loaded MessageSearch mod v{VERSION} by Malex")
