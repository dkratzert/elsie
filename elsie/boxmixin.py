import base64
import io
import logging
from typing import List, TYPE_CHECKING, Union

import lxml.etree as et
from PIL import Image

from .draw import draw_bitmap, set_paint_style
from .highlight import highlight_code
from .image import get_image_steps, create_image_data
from .lazy import eval_value, unpack_point, eval_pair
from .path import (
    check_and_unpack_path_commands,
    eval_path_commands,
    path_points_for_end_arrow,
    path_update_end_point,
)

from .show import ShowInfo
from .svg import svg_size_to_pixels
from .textparser import (
    parse_text,
    add_line_numbers,
    tokens_merge,
    tokens_to_text_without_style,
)
from .ora import convert_ora_to_svg

if TYPE_CHECKING:
    from . import arrow, lazy, boxitem, textboxitem
    from .box import Box


def scaler(rect, image_width, image_height):
    scale_x = rect.width / image_width
    scale_y = rect.height / image_height

    if rect.width and rect.height:
        return min(scale_x, scale_y)
    elif rect.width:
        return scale_x
    elif rect.height:
        return scale_y
    return None


class BoxMixin:
    """This mixin contains the most important methods of box-like elements (boxes and box
    items).
    """

    def _get_box(self):
        raise NotImplementedError

    def box(
        self,
        x: float = None,
        y: float = None,
        width: float = None,
        height: float = None,
        *,
        show: str = None,
        p_left: float = None,
        p_right: float = None,
        p_top: float = None,
        p_bottom: float = None,
        p_x: float = None,
        p_y: float = None,
        padding: float = None,
        horizontal=False,
        z_level: int = None,
        prepend=False,
        above: "BoxMixin" = None,
        below: "BoxMixin" = None,
        name: str = None,
    ) -> "Box":
        """
        Creates a new child box.

        Parameters
        ----------
        x: float
            X position of the box.
        y: float
            Y position of the box.

            Possible values: None, number, "NN", "NN%", "[NN%]", or a dynamic coordinate,
            where NN is a number.
        width: float
            Width of the box.
        height: float
            Height of the box.

            Possible values: None, number, "NN", "NN%", "fill", "fill(NN)".

        show: str
            Fragment selector that decides in which fragments should the box be visible.

            Possible values: None, a number, "XX-XX", "XX+" where XX is a number, "next" or "last"
        p_left: float
            Left padding of the box.
        p_right: float
            Right padding of the box.
        p_top: float
            Top padding of the box.
        p_bottom: float
            Bottom padding of the box.
        p_x: float
            Sets both left and right padding of the box.
        p_y: float
            Sets both top and bottom padding of the box.
        padding: float
            Sets all four padding values of the box (left, right, top, bottom):
        horizontal: bool
            If True, use horizontal layout: children will be placed in a row.
            If False, use vertical layout (the default): children will be placed in a column.
        z_level: int
            Sets the Z-level of the box.
                If None, the parent z_level will be used.
                z_level of the top-level box is 0.
                If z_level is X then all boxes with a *smaller* z_level than X is painted before
                this box.
        prepend: bool
            If True, the new box is inserted as the first child of its parent.
            Otherwise it is inserted as the last child.
        above: Box
            The new box will be inserted into its parent right after the passed box.
            The passed box has to be a child of the parent box.
        below: Box
            The new box will be inserted into its parent right before the passed box.
            The passed box has to be a child of the parent box.
        name: str
            Name of the box (used for debugging purposes).
        """
        box = self._get_box()
        layout = box.layout.add(
            x=x,
            y=y,
            width=width,
            height=height,
            p_left=p_left,
            p_right=p_right,
            p_top=p_top,
            p_bottom=p_bottom,
            p_x=p_x,
            p_y=p_y,
            padding=padding,
            horizontal=horizontal,
            prepend=prepend,
        )

        if z_level is None:
            z_level = box.z_level

        show = ShowInfo.parse(show, box.slide.max_step)
        box.slide.max_step = max(box.slide.max_step, show.max_step())

        new_box = box.__class__(box.slide, layout, box._styles, show, z_level, name)
        box.add_child(new_box, prepend, above, below)
        return new_box

    def overlay(self, **kwargs) -> "Box":
        """
        Shortcut for `box(x=0, y=0, width="100%", height="100%")`.

        The resulting box will overlay the whole area of the current box."""
        kwargs.setdefault("x", 0)
        kwargs.setdefault("y", 0)
        kwargs.setdefault("width", "100%")
        kwargs.setdefault("height", "100%")
        return self.box(**kwargs)

    def fbox(self, **kwargs) -> "Box":
        """
        Shortcut for `box(width="fill", height="fill")`.

        fbox means "fill box"."""
        kwargs.setdefault("width", "fill")
        kwargs.setdefault("height", "fill")
        return self.box(**kwargs)

    def sbox(self, **kwargs) -> "Box":
        """
        Shortcut for `box(height="fill")` if the layout is horizontal or `box(width="fill")`
        if the layout is vertical.

        sbox means "spread box"."""
        if self.layout.horizontal:
            kwargs.setdefault("height", "fill")
        else:
            kwargs.setdefault("width", "fill")
        return self.box(**kwargs)

    def rect(
        self,
        color=None,
        bg_color=None,
        stroke_width=1,
        stroke_dasharray=None,
        rx=None,
        ry=None,
    ) -> "boxitem.BoxItem":
        """
        Draws a rectangle around the box.

        Parameters
        ----------
        color: str
            Color of the rectangle edge.
        bg_color: str
            Color of the rectangle background.
        stroke_width: float
            Width of the rectangle edge.
        stroke_dasharray: str
            SVG dash effect of the rectangle edge.
        rx: float
            x-axis radius of the rectangle. Use it if you want rounded corners.
        ry: float
            x-axis radius of the rectangle. Use it if you want rounded corners.
        """

        def draw(ctx):
            rect = self._get_box().layout.rect
            xml = ctx.xml
            xml.element("rect")
            xml.set("x", rect.x)
            xml.set("y", rect.y)
            xml.set("width", rect.width)
            xml.set("height", rect.height)
            if rx:
                xml.set("rx", rx)
            if ry:
                xml.set("ry", ry)
            set_paint_style(xml, color, bg_color, stroke_width, stroke_dasharray)
            xml.close("rect")

        return self._create_simple_box_item(draw)

    def polygon(
        self,
        points,
        color: str = None,
        bg_color: str = None,
        stroke_width=1,
        stroke_dasharray: str = None,
    ) -> "boxitem.BoxItem":
        """
        Draws a polygon.

        Parameters
        ----------
        points: list
            List of points of the polygon.
            Each point can be either a 2-element tuple/list with (x, y) coordinates or a
            `value.LazyPoint`.
        color: str
            Color of the edge of the polygon.
        bg_color: str
            Color of the background of the polygon.
        stroke_width: float
            Width of the edge of the polygon.
        stroke_dasharray: str
            SVG dash effect of the edge of the polygon.
        """

        def draw(ctx):
            xml = ctx.xml
            xml.element("polygon")
            xml.set(
                "points",
                " ".join(
                    "{},{}".format(eval_value(x), eval_value(y)) for x, y in points
                ),
            )
            set_paint_style(xml, color, bg_color, stroke_width, stroke_dasharray)
            xml.close("polygon")

        points = [unpack_point(p, self) for p in points]
        return self._create_simple_box_item(draw)

    def path(
        self,
        commands,
        color="black",
        bg_color: str = None,
        stroke_width=1,
        stroke_dasharray: str = None,
        end_arrow: "arrow.Arrow" = None,
    ) -> "boxitem.BoxItem":
        """
        Draws a SVG path.

        Parameters
        ----------
        commands: List[str]
            SVG draw commands.
        color: str
            Color of the path.
        bg_color: str
            Background color of the path.
        stroke_width: float
            Width of the path.
        stroke_dasharray: str
            SVG dash effect of the path.
        end_arrow: "arrow.Arrow"
            End arrow of the path.
        """
        commands = check_and_unpack_path_commands(commands, self)
        if not commands:
            return self

        def command_to_str(command):
            name, pairs = command
            return name + " ".join("{},{}".format(p[0], p[1]) for p in pairs)

        def draw(ctx):
            cmds = eval_path_commands(commands)
            if end_arrow:
                end_p1, end_p2 = path_points_for_end_arrow(cmds)
                end_new_p2 = end_arrow.move_end_point(end_p1, end_p2)
                path_update_end_point(cmds, end_new_p2)

            xml = ctx.xml
            xml.element("path")
            xml.set("d", " ".join(command_to_str(c) for c in cmds))
            set_paint_style(xml, color, bg_color, stroke_width, stroke_dasharray)
            xml.close("path")

            if end_arrow:
                end_arrow.render(xml, end_p1, end_p2, color)

        return self._create_simple_box_item(draw)

    def line(
        self,
        points,
        color="black",
        stroke_width=1,
        stroke_dasharray: str = None,
        start_arrow: "arrow.Arrow" = None,
        end_arrow: "arrow.Arrow" = None,
    ) -> "boxitem.BoxItem":
        """
        Draws a line.

        Parameters
        ----------
        points: List[(float, float) | "value.LazyPoint"]
            List of at least two points.
        color: str
            Color of the line.
        stroke_width: float
            Width of the lne.
        stroke_dasharray: str
            SVG dash effect of the lne.
        start_arrow: "arrow.Arrow"
            Start arrow of the line.
        end_arrow: "arrow.Arrow"
            End arrow of the line.
        """

        def draw(ctx):
            p = [eval_pair(p) for p in points]
            p2 = p[:]

            if start_arrow:
                p2[0] = start_arrow.move_end_point(p[1], p[0])
            if end_arrow:
                p2[-1] = end_arrow.move_end_point(p[-2], p[-1])

            xml = ctx.xml
            xml.element("polyline")
            xml.set("points", " ".join("{},{}".format(x, y) for x, y in p2))
            set_paint_style(xml, color, None, stroke_width, stroke_dasharray)
            xml.close("polyline")

            if start_arrow:
                start_arrow.render(xml, p[1], p[0], color)

            if end_arrow:
                end_arrow.render(xml, p[-2], p[-1], color)

        assert len(points) >= 2
        points = [unpack_point(p, self) for p in points]
        return self._create_simple_box_item(draw)

    def _create_simple_box_item(self, render_fn):
        box = self._get_box()
        item = SimpleBoxItem(box, render_fn)
        box.add_child(item)
        return item

    def _render_svg(self, ctx, x, y, scale, data):
        ctx.xml.element("g")
        transform = ["translate({}, {})".format(x, y)]
        if scale != 1.0:
            transform.append("scale({})".format(scale))
        ctx.xml.set("transform", " ".join(transform))
        ctx.xml.raw_text(data)
        ctx.xml.close()

    def image(
        self,
        filename: str,
        scale: float = None,
        fragments=True,
        show_begin=1,
        select_steps: List[Union[int, None]] = None,
    ) -> "boxitem.BoxItem":
        """Draws an SVG/PNG/JPEG/ORA image, detected by the extension of the `filename`.

        Parameters
        ----------
        filename: str
            Filename of the image.
        scale: float
            Scale of the resulting image.
            < 1.0 -> Smaller size.
            = 1.0 -> Original size.
            > 1.0 -> Larger size.
        fragments: bool
            Load fragments from the image (only applicable for SVG and ORA images).
        show_begin: int
            Fragment from which will the image fragments be shown.
            Only applicable if `fragments` is set to True.
        select_steps: List[Union[int, None]]
            Select which fragments of the image should be drawn at the given fragments of the
            slide.

            `select_steps=[1, 3, None, 2]`
            Would render the first image fragment in the first slide fragment, the third image
            fragment in the second slide fragment, no image fragment in the third slide fragment
            and the second image fragment in the fourth slide fragment.
        """
        if filename.endswith(".svg"):
            return self._image_svg(filename, scale, fragments, show_begin, select_steps)
        elif filename.endswith(".ora"):
            return self._image_ora(filename, scale, fragments, show_begin, select_steps)
        elif any(filename.endswith(ext) for ext in [".png", ".jpeg", ".jpg"]):
            return self._image_bitmap(filename, scale)
        else:
            raise Exception("Unkown image extension")

    def _image_bitmap(self, filename, scale):
        key = (filename, "bitmap")
        entry = self._get_box().slide.temp_cache.get(key)

        if entry is None:
            with open(filename, "rb") as f:
                data = f.read()

            img = Image.open(io.BytesIO(data))
            mime = Image.MIME[img.format]
            image_width, image_height = img.size
            del img

            data = base64.b64encode(data).decode("ascii")
            self._get_box().slide.temp_cache[key] = (
                image_width,
                image_height,
                mime,
                data,
            )
        else:
            image_width, image_height, mime, data = entry

        self._get_box().layout.set_image_size_request(
            image_width * (scale or 1), image_height * (scale or 1)
        )

        def draw(ctx):
            rect = self._get_box().layout.rect
            if scale is None:
                s = scaler(rect, image_width, image_height)
                if s is None:
                    s = 0
                    logging.warning(
                        "Scale of image {} is 0, set scale explicitly or set at least one "
                        "dimension for the parent box".format(filename)
                    )
            else:
                s = scale

            w = image_width * s
            h = image_height * s
            x = rect.x + (rect.width - w) / 2
            y = rect.y + (rect.height - h) / 2
            draw_bitmap(ctx.xml, x, y, w, h, mime, data)

        return self._create_simple_box_item(draw)

    def _image_ora(self, filename, scale, fragments, show_begin, select_steps):
        key = (filename, "svg")
        slide = self._get_box().slide
        if key not in slide.temp_cache:

            def constructor(_content, output, _data_type):
                svg = convert_ora_to_svg(filename)
                with open(output, "w") as f:
                    f.write(svg)

            cache_file = slide.fs_cache.ensure_by_file(filename, "svg", constructor)
            self._get_box().slide.temp_cache[key] = et.parse(cache_file).getroot()
        return self._image_svg(filename, scale, fragments, show_begin, select_steps)

    def _image_svg(
        self,
        filename: str,
        scale: float = None,
        fragments=True,
        show_begin=1,
        select_steps: List[int] = None,
    ):
        """ Draw an svg image """

        key = (filename, "svg")
        root = self._get_box().slide.temp_cache.get(key)
        if root is None:
            root = et.parse(filename).getroot()
            self._get_box().slide.temp_cache[key] = root

        image_width = svg_size_to_pixels(root.get("width"))
        image_height = svg_size_to_pixels(root.get("height"))

        self._get_box().layout.set_image_size_request(
            image_width * (scale or 1), image_height * (scale or 1)
        )

        if select_steps is not None:
            image_steps = len(select_steps)
        else:
            if fragments:
                image_steps = get_image_steps(root)
            else:
                image_steps = 1

        self._get_box()._ensure_steps(show_begin - 1 + image_steps)

        image_data = None

        if image_steps == 1 and not select_steps:
            image_data = et.tostring(root).decode()

        def draw(ctx):
            rect = self._get_box().layout.rect

            if image_data is None:
                step = ctx.step - show_begin + 1
                if select_steps is not None:
                    if 0 < step <= len(select_steps):
                        step = select_steps[step - 1]
                    else:
                        return
                    if step is None:
                        return
                if step < 1:
                    return
                data = create_image_data(root, step)
            else:
                if ctx.step < show_begin:
                    return
                data = image_data

            if scale is None:
                s = scaler(rect, image_width, image_height)
                if s is None:
                    s = 0
                    logging.warning(
                        "Scale of image {} is 0, set scale explicitly or set at least one "
                        "dimension for the parent box".format(filename)
                    )
            else:
                s = scale

            w = image_width * s
            h = image_height * s
            x = rect.x + (rect.width - w) / 2
            y = rect.y + (rect.height - h) / 2
            self._render_svg(ctx, x, y, s, data)

        return self._create_simple_box_item(draw)

    def code(
        self,
        language: str,
        text: str,
        *,
        tabsize=4,
        line_numbers=False,
        style="code",
        use_styles=False,
        escape_char="~",
        scale_to_fit=False,
    ) -> "textboxitem.TextBoxItem":
        """
        Draws a code snippet with syntax highlighting.

        Parameters
        ----------
        language: str
            Language used for syntax highlighting.
        text: str
            Content of the code snippet.
        tabsize: int
            Number of spaces generated by tab characeters.
        line_numbers: bool
            If True, line numbers will be drawn in the code snippet.
        style: str
            Name of style used for drawing the code snippet.
        use_styles: bool
            If True, inline styles will be evaluated in the code snippet.
        escape_char: str
            Escape character for creating inline styles in the code snippet.
        scale_to_fit: bool
            If True, scales the code snippet to fit its parent box.
        """
        text = text.replace("\t", " " * tabsize)

        if language:
            if use_styles:
                # pygments strips newlines at the beginning
                # of whole text
                # and it makes a problem with mering styles
                # therefore we strips newlines right away

                start_newlines = 0
                while text.startswith("\n"):
                    start_newlines += 1
                    text = text[1:]

                ptext = parse_text(text, escape_char)
                text = tokens_to_text_without_style(ptext)
            parsed_text = highlight_code(text, language)
            if use_styles:
                parsed_text = tokens_merge(parsed_text, ptext)
                if start_newlines:
                    parsed_text.insert(0, ("newline", start_newlines))
        else:
            parsed_text = parse_text(
                text, escape_char=escape_char if use_styles else None
            )

        if line_numbers:
            parsed_text = add_line_numbers(parsed_text)

        style = self._get_box().get_style(style, full_style=True)
        return self._text_helper(parsed_text, style, scale_to_fit)

    def text(
        self, text: str, style="default", *, escape_char="~", scale_to_fit=False
    ) -> "textboxitem.TextBoxItem":
        """
        Draws text.

        Parameters
        ----------
        text: str
            Text content that will be drawn.
        style: str | `textstyle.TextStyle`
            Name of a style or an instance of `textstyle.TextStyle` that will be used to style the
            text.
        escape_char: str
            Escape character for creating inline styles in the text.
        scale_to_fit:
            If True, scales the text to fit its parent box.
        """
        result_style = self._get_box().get_style(style, full_style=True)
        parsed_text = parse_text(text, escape_char=escape_char)
        return self._text_helper(parsed_text, result_style, scale_to_fit)

    def _text_helper(self, parsed_text, style, scale_to_fit):
        box = self._get_box()
        item = TextBoxItem(box, parsed_text, style, box._styles, scale_to_fit)
        box.add_child(item)
        return item

    def latex(
        self, text: str, scale=1.0, header: str = None, tail: str = None
    ) -> "boxitem.BoxItem":
        """
        Renders LaTeX.

        Parameters
        ----------
        text: str
            Source code of the LaTeX snippet.
        scale: float
            Scale of the rendered output.
        header: str
            Prelude of the LaTeX source (for example package imports).
            Will be included at the beginning of the source code.
        tail: str
            End of the LaTeX source (for example end the document).
            Will be included at the end of the source code.
        """

        if header is None:
            header = """
\\documentclass[varwidth,border=1pt]{standalone}
\\usepackage[utf8x]{inputenc}
\\usepackage{ucs}
\\usepackage{amsmath}
\\usepackage{amsfonts}
\\usepackage{amssymb}
\\usepackage{graphicx}
\\begin{document}"""

        if tail is None:
            tail = "\\end{document}"

        tex_text = "\n".join((header, text, tail))

        def draw(ctx):
            rect = self._get_box().layout.rect
            x = rect.x + (rect.width - svg_width) / 2
            y = rect.y + (rect.height - svg_height) / 2
            self._render_svg(ctx, x, y, scale, svg)

        svg = self._get_box().slide.slides.process_query("latex", tex_text)
        root = et.fromstring(svg)
        svg_width = svg_size_to_pixels(root.get("width")) * scale
        svg_height = svg_size_to_pixels(root.get("height")) * scale

        self._get_box().layout.ensure_width(svg_width)
        self._get_box().layout.ensure_height(svg_height)

        return self._create_simple_box_item(draw)

    def x(self, value) -> "lazy.LazyValue":
        """Create a lazy value relative to the left edge of the box."""
        return self._get_box().layout.x(value)

    def y(self, value) -> "lazy.LazyValue":
        """Create a lazy value relative to the top edge of the box."""
        return self._get_box().layout.y(value)

    def p(self, x, y) -> "lazy.LazyPoint":
        """Create a lazy point relative to the top-left corner of the box."""
        return self._get_box().layout.point(x, y)

    def mid_point(self) -> "lazy.LazyPoint":
        """Create a lazy point that resolves to the center of the box."""
        return self.p("50%", "50%")


from .boxitem import SimpleBoxItem  # noqa
from .textboxitem import TextBoxItem  # noqa
