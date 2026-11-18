"""A single prompt buffer in the sidebar on Blender versions before UILayout.textbox."""

from bisect import bisect_right
from dataclasses import dataclass

import blf
import bpy
import gpu
from bpy.app.handlers import persistent
from bpy.props import IntProperty
from gpu_extras.batch import batch_for_shader



PROMPT_LIMIT = 1500
_editor = None


def _width(text):
    return blf.dimensions(0, text.expandtabs(4))[0]


def _wrap(value, width):
    """Visual lines reference the original buffer, including whitespace at wraps."""
    lines = []
    start = 0
    for line in value.split('\n'):
        end = start + len(line)
        while _width(value[start:end]) > width and start < end:
            low, high = start + 1, end
            while low < high:
                middle = (low + high + 1) // 2
                if _width(value[start:middle]) <= width:
                    low = middle
                else:
                    high = middle - 1
            space = value.rfind(' ', start + 1, low)
            split = space + 1 if space >= start else low
            lines.append((start, split))
            start = split
        lines.append((start, end))
        start = end + 1
    return lines


def draw_prompt(layout, context, settings):
    box = layout.box()
    header = box.row(align=True)
    header.label(text='Editing Notes', icon='TEXT')
    header.operator('easykig.paste_editing_prompt', text='Paste', icon='PASTEDOWN')
    header.operator('easykig.paste_editing_prompt', text='', icon='X').clear = True
    value = settings.editing_prompt
    if hasattr(box, 'textbox'):
        box.textbox(settings, 'editing_prompt', initial_visible_lines=5, placeholder='Notes for text-conditioned editing')
    else:
        body = box.box().column(align=True)
        body.operator_context = 'INVOKE_DEFAULT'
        scale = context.preferences.system.ui_scale
        blf.size(0, round(12 * scale))
        lines = _wrap(value, max(30, context.region.width - 70 * scale))
        for index in range(min(5, max(3, len(lines)))):
            start, end = lines[index] if index < len(lines) else (len(value), len(value))
            label = value[start:end] or ('Type or paste editing notes' if not value and index == 0 else ' ')
            row = body.row()
            row.alignment = 'LEFT'
            row.operator('easykig.edit_editing_prompt', text=label.expandtabs(4), emboss=False, translate=False).offset = start
        if len(lines) > 5:
            body.operator('easykig.edit_editing_prompt', text='…', emboss=False).offset = lines[5][0]
    if len(value) > PROMPT_LIMIT:
        box.label(text=f'{len(value):,} / {PROMPT_LIMIT:,} characters', icon='ERROR')


@dataclass
class _Layout:
    left: float
    right: float
    top: float
    bottom: float
    step: float
    pad: float
    count: int
    lines: list

    @property
    def text_x(self):
        return self.left + self.pad

    @property
    def text_top(self):
        return self.top - 1.5 * self.step


def _rectangle(shader, x, y, right, top, color):
    shader.bind()
    shader.uniform_float('color', color)
    batch_for_shader(shader, 'TRI_FAN', {'pos': [(x, y), (right, y), (right, top), (x, top)]}).draw(shader)


def _draw_text(x, y, text, color):
    blf.color(0, *color)
    blf.position(0, x, y, 0)
    blf.draw(0, text.expandtabs(4))


class EASYKIG_OT_edit_editing_prompt(bpy.types.Operator):
    bl_idname = 'easykig.edit_editing_prompt'
    bl_label = 'Edit Prompt'
    bl_description = 'Edit the multiline prompt. Ctrl+Enter applies; Esc cancels'
    offset: IntProperty(options={'HIDDEN', 'SKIP_SAVE'}, min=0)

    @classmethod
    def poll(cls, context):
        return (
            context.area and context.area.type == 'VIEW_3D'
            and context.region and context.region.type == 'UI'
            and context.region.active_panel_category == 'EasyKig'
        )

    def invoke(self, context, event):
        global _editor
        if _editor is not None:
            return {'CANCELLED'}
        self._scene = context.scene
        self._area = context.area
        self._region = context.region
        self._top = event.mouse_region_y + 48 * context.preferences.system.ui_scale
        self.value = context.scene.easykig_settings.editing_prompt.replace('\r\n', '\n').replace('\r', '\n')
        self.caret = self.anchor = min(self.offset, len(self.value))
        self.history = []
        self.redo = []
        self.first = 0
        self.dragging = False
        self.notice = ''
        self._closed = False
        self._reveal(self._layout(context))
        self._handler = bpy.types.SpaceView3D.draw_handler_add(self._draw, (), 'UI', 'POST_PIXEL')
        _editor = self
        context.window_manager.modal_handler_add(self)
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _layout(self, context):
        scale = context.preferences.system.ui_scale
        pad, step = 9 * scale, 20 * scale
        font_size = max(10, round(13 * scale))
        blf.size(0, font_size)
        count = max(1, min(6, int((self._region.height - 2 * pad) / step - 2.5)))
        height = (count + 2.5) * step
        top = min(self._region.height - pad, max(height + pad, self._top))
        right = self._region.width - 2 * pad
        lines = _wrap(self.value, max(25, right - 3 * pad))
        return _Layout(pad, right, top, top - height, step, pad, count, lines)

    def _line(self, layout):
        return bisect_right([start for start, _ in layout.lines], self.caret) - 1

    def _reveal(self, layout):
        index = self._line(layout)
        self.first = max(0, min(self.first, index, len(layout.lines) - layout.count))
        self.first = max(self.first, index - layout.count + 1)

    def _draw(self):
        context = bpy.context
        if context.area != self._area or context.region != self._region:
            return
        layout = self._layout(context)
        if layout.right <= layout.left:
            return
        self.first = min(self.first, max(0, len(layout.lines) - layout.count))
        widget = context.preferences.themes[0].user_interface.wcol_text
        text = (*widget.text[:3], 1)
        fill = (*widget.inner[:3], 1)
        selection = (*widget.inner_sel[:3], 1)
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        _rectangle(shader, layout.left, layout.bottom, layout.right, layout.top, selection)
        _rectangle(shader, layout.left + 1, layout.bottom + 1, layout.right - 1, layout.top - 1, fill)
        _draw_text(layout.text_x, layout.top - layout.step, 'Editing Notes', text)
        done = 'Apply'
        right = layout.right - layout.pad
        button_x = right - _width(done)
        _rectangle(shader, button_x - .5 * layout.pad, layout.text_top + 1,
                   right + .5 * layout.pad, layout.top - .25 * layout.step, selection)
        _draw_text(button_x, layout.top - layout.step, done, text)

        lo, hi = sorted((self.anchor, self.caret))
        caret_row = self._line(layout)
        for index, (start, end) in enumerate(layout.lines[self.first:self.first + layout.count], self.first):
            top = layout.text_top - (index - self.first) * layout.step
            y = top - .76 * layout.step
            x = layout.text_x
            if lo < end and hi > start and lo != hi:
                a = x + _width(self.value[start:max(lo, start)])
                b = x + _width(self.value[start:min(hi, end)])
                _rectangle(shader, a, top - layout.step, b, top, selection)
            _draw_text(x, y, self.value[start:end], text)
            if index == caret_row:
                x += _width(self.value[start:self.caret])
                _rectangle(shader, x, top - layout.step + 2, x + 1.5, top - 2, text)
        footer = self.notice or ('Ctrl+Enter Apply   Esc Cancel' if layout.right - layout.left > 205 * layout.pad / 9 else 'Esc Cancel')
        _draw_text(layout.text_x, layout.bottom + .34 * layout.step, footer, text)

    def _close(self, commit):
        global _editor
        if self._closed:
            return
        self._closed = True
        _editor = None
        bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'UI')
        try:
            if commit:
                self._scene.easykig_settings.editing_prompt = self.value
            self._area.tag_redraw()
        except ReferenceError:
            pass

    def cancel(self, context):
        self._close(False)

    def _state(self):
        return self.value, self.anchor, self.caret

    def _replace(self, insert, start=None, end=None):
        lo, hi = sorted((self.anchor, self.caret)) if start is None else (start, end)
        insert = insert.replace('\r\n', '\n').replace('\r', '\n')
        new = self.value[:lo] + insert + self.value[hi:]
        if len(new) > PROMPT_LIMIT and len(new) >= len(self.value):
            self.notice = f'{PROMPT_LIMIT:,} character limit'
            return
        if new != self.value:
            self.history.append(self._state())
            self.history = self.history[-64:]
            self.redo.clear()
            self.value = new
        self.caret = self.anchor = lo + len(insert)
        self.notice = ''

    def _move(self, offset, extend):
        self.caret = max(0, min(offset, len(self.value)))
        if not extend:
            self.anchor = self.caret

    def _hit(self, line, x):
        start, end = line
        before = 0
        for index in range(start, end):
            after = _width(self.value[start:index + 1])
            if x < (before + after) / 2:
                return index
            before = after
        return end

    def _mouse(self, layout, x, y, extend):
        row = int((layout.text_top - y) // layout.step)
        index = max(0, min(self.first + min(row, layout.count - 1), len(layout.lines) - 1))
        self._move(self._hit(layout.lines[index], x - layout.text_x), extend)

    def _keys(self, context, event, layout):
        key = event.type
        ctrl = event.ctrl or event.oskey
        lo, hi = sorted((self.anchor, self.caret))
        if ctrl and key == 'A':
            self.anchor, self.caret = 0, len(self.value)
        elif ctrl and key in {'C', 'X'}:
            if lo != hi:
                context.window_manager.clipboard = self.value[lo:hi]
                if key == 'X':
                    self._replace('')
        elif ctrl and key == 'V':
            self._replace(context.window_manager.clipboard)
        elif ctrl and key in {'Z', 'Y'}:
            redo = key == 'Y' or event.shift
            source, destination = (self.redo, self.history) if redo else (self.history, self.redo)
            if source:
                destination.append(self._state())
                self.value, self.anchor, self.caret = source.pop()
        elif key in {'BACK_SPACE', 'DEL'}:
            if lo == hi:
                lo = max(0, lo - int(key == 'BACK_SPACE'))
                hi = min(len(self.value), hi + int(key == 'DEL'))
            self._replace('', lo, hi)
        elif key in {'RET', 'NUMPAD_ENTER'}:
            self._replace('\n')
        elif key in {'LEFT_ARROW', 'RIGHT_ARROW'}:
            delta = -1 if key == 'LEFT_ARROW' else 1
            end = lo if delta < 0 else hi
            self._move(end if lo != hi and not event.shift else self.caret + delta, event.shift)
        elif key in {'UP_ARROW', 'DOWN_ARROW'}:
            row = self._line(layout)
            target = max(0, min(row + (-1 if key == 'UP_ARROW' else 1), len(layout.lines) - 1))
            x = _width(self.value[layout.lines[row][0]:self.caret])
            self._move(self._hit(layout.lines[target], x), event.shift)
        elif key == 'HOME':
            self._move(0 if ctrl else self.value.rfind('\n', 0, self.caret) + 1, event.shift)
        elif key == 'END':
            end = self.value.find('\n', self.caret)
            self._move(len(self.value) if ctrl or end == -1 else end, event.shift)
        elif not ctrl and event.unicode and event.unicode.isprintable():
            self._replace(event.unicode)
        else:
            return False
        return True

    def modal(self, context, event):
        if self._closed:
            return {'CANCELLED'}
        if context.scene != self._scene or context.area != self._area or not self._area.spaces.active.show_region_ui:
            self._close(False)
            return {'CANCELLED', 'PASS_THROUGH'}
        if event.type == 'ESC' and event.value == 'PRESS':
            self._close(False)
            return {'CANCELLED'}
        if event.type in {'RET', 'NUMPAD_ENTER', 'S'} and (event.ctrl or event.oskey) and event.value == 'PRESS':
            self._close(True)
            return {'FINISHED', 'PASS_THROUGH'} if event.type == 'S' else {'FINISHED'}
        layout = self._layout(context)
        x, y = event.mouse_x - self._region.x, event.mouse_y - self._region.y
        inside = layout.left <= x <= layout.right and layout.bottom <= y <= layout.top
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                if not inside or (y > layout.text_top and x > layout.right - 6 * layout.pad):
                    self._close(True)
                    return {'FINISHED'} if inside else {'FINISHED', 'PASS_THROUGH'}
                if layout.bottom + layout.step <= y <= layout.text_top:
                    self.dragging = True
                    self._mouse(layout, x, y, event.shift)
            elif event.value == 'RELEASE':
                self.dragging = False
        elif event.type == 'MOUSEMOVE' and self.dragging:
            self._mouse(layout, x, y, True)
        elif inside and event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            delta = -1 if event.type == 'WHEELUPMOUSE' else 1
            self.first = max(0, min(self.first + delta, len(layout.lines) - layout.count))
        elif event.value == 'PRESS' and self._keys(context, event, layout):
            self._reveal(self._layout(context))
        else:
            return {'PASS_THROUGH'}
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}


@persistent
def _cancel_prompt(_file):
    if _editor is not None:
        _editor._close(False)


def register():
    bpy.utils.register_class(EASYKIG_OT_edit_editing_prompt)
    bpy.app.handlers.load_pre.append(_cancel_prompt)


def unregister():
    _cancel_prompt(None)
    bpy.app.handlers.load_pre.remove(_cancel_prompt)
    bpy.utils.unregister_class(EASYKIG_OT_edit_editing_prompt)
