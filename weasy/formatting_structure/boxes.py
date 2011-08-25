# coding: utf8

#  WeasyPrint converts web documents (HTML, CSS, ...) to PDF.
#  Copyright (C) 2011  Simon Sapin
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as
#  published by the Free Software Foundation, either version 3 of the
#  License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Classes for all types of boxes in the CSS formatting structure / box model.

See http://www.w3.org/TR/CSS21/visuren.html

Names are the same as in CSS 2.1 with the exception of ``TextBox``. In
WeasyPrint, any text is in a ``TextBox``. What CSS calls anonymous inline boxes
are text boxes but not all text boxes are anonymous inline boxes.

See http://www.w3.org/TR/CSS21/visuren.html#anonymous

Abstract classes, should not be instantiated:

 * Box
 * BlockLevelBox
 * InlineLevelBox
 * BlockContainerBox
 * AnonymousBox
 * ReplacedBox
 * ParentBox
 * AtomicInlineLevelBox

Concrete classes:

 * PageBox
 * BlockBox
 * AnonymousBlockBox
 * InlineBox
 * InlineBlockBox
 * BlockLevelReplacedBox
 * InlineLevelReplacedBox
 * TextBox
 * LineBox

Apart from :class:`PageBox` and :class:`LineBox`, all concrete box classes have
one of the following "outside" behavior:

 * Block-level (inherits from :class:`BlockLevelBox`)
 * Inline-level (inherits from :class:`InlineLevelBox`)

and one of the following "inside" behavior:

 * Block container (inherits from :class:`BlockContainerBox`)
 * Inline content (InlineBox and :class:`TextBox`)
 * Replaced content (inherits from :class:`ReplacedBox`)

See respective docstrings for details.

"""


import collections

from ..css import computed_from_cascaded
from ..css.values import get_single_keyword


# The *Box classes have many attributes and methods, but that's the way it is
# pylint: disable=R0904,R0902

class Box(object):
    """Abstract base class for all boxes."""

    class __metaclass__(type):
        """
        Metaclass that adds a :attr:`_all_slots` attribute to Box sub-classes:
        the concatenation of the class and its ancestors’s :attr:`__slots__`
        """
        def __new__(cls, name, bases, dct):
            new_class = type.__new__(cls, name, bases, dct)
            new_class._all_slots = tuple(
                name
                for class_ in bases
                if class_ is not object
                for name in class_._all_slots
            ) + new_class.__slots__
            return new_class

    __slots__ = (
        'document', 'element', 'parent', 'width', 'height',
        'position_x', 'position_y', 'style', 'text_indent',
        'min_width', 'max_width', 'min_height', 'max_height',
        'background_drawn',
        # Should be on some sub-classes only, but put these here to avoid
        # 'multiple bases have instance lay-out conflict'
        'children', 'baseline'
    ) + tuple(
        template % side
        for template in ['padding_%s', 'border_%s_width', 'margin_%s']
        for side in ['top', 'right', 'bottom', 'left']
    )

    def __init__(self, document, element):
        self.document = document
        # Should never be None
        self.element = element
        # No parent yet. Will be set when this box is added to another box’s
        # children. Only the root box should stay without a parent.
        self.parent = None
        self._init_style()
        self.width = None
        self.height = None
        self.position_x = 0
        self.position_y = 0

    def _init_style(self):
        """Initialize the style."""
        # Computed values
        # Copying might not be needed, but let’s be careful with mutable
        # objects.
        self.style = self.document.style_for(self.element).copy()

    def __repr__(self):
        return '<%s %s %i>' % (
            type(self).__name__, self.element.tag, self.element.sourceline)

    def ancestors(self):
        """Yield parent and recursively yield parent's parents."""
        parent = self
        while parent.parent:
            parent = parent.parent
            yield parent

    def containing_block_size(self):
        """``(width, height)`` size of the box's containing block."""
        if isinstance(self.parent, PageBox):
            return self.parent.width, self.parent.height

        position = get_single_keyword(self.style.position)
        if position in ('relative', 'static'):
            return self.parent.width, self.parent.height
        elif position == 'fixed':
            for ancestor in self.ancestors():
                if isinstance(ancestor, PageBox):
                    return ancestor.width, ancestor.height
            assert False, 'Page not found'
        elif position == 'absolute':
            for ancestor in self.ancestors():
                position = get_single_keyword(ancestor.style.position)
                if position in ('absolute', 'relative', 'fixed'):
                    display = get_single_keyword(ancestor.style.display)
                    if display == 'inline':
                        # TODO: fix this bad behaviour, see CSS 10.1
                        return ancestor.width, ancestor.height
                    else:
                        return ancestor.width, ancestor.height
                elif isinstance(ancestor, PageBox):
                    return ancestor.width, ancestor.height
        assert False, 'Containing block not found'

    def copy(self):
        """Return shallow copy of the box."""
        cls = type(self)
        # Create a new instance without calling __init__: initializing
        # styles may be kinda expensive, no need to do it again.
        new_box = cls.__new__(cls)
        # Copy attributes
        for name in self._all_slots:
            try:
                value = getattr(self, name)
            except AttributeError:
                pass
            else:
                setattr(new_box, name, value)
        new_box.style = self.style.copy()
        return new_box

    def translate(self, x, y):
        """Change the box’s position.

        Also update the children’s positions accordingly.

        """
        # Overridden in ParentBox to also translate children, if any.
        self.position_x += x
        self.position_y += y

    # Heights and widths

    def padding_width(self):
        """Width of the padding box."""
        return self.width + self.padding_left + self.padding_right

    def padding_height(self):
        """Height of the padding box."""
        return self.height + self.padding_top + self.padding_bottom

    def border_width(self):
        """Width of the border box."""
        return self.padding_width() + self.border_left_width + \
            self.border_right_width

    def border_height(self):
        """Height of the border box."""
        return self.padding_height() + self.border_top_width + \
            self.border_bottom_width

    def margin_width(self):
        """Width of the margin box (aka. outer box)."""
        return self.border_width() + self.margin_left + self.margin_right

    def margin_height(self):
        """Height of the margin box (aka. outer box)."""
        return self.border_height() + self.margin_top + self.margin_bottom

    def horizontal_surroundings(self):
        """Sum of all horizontal margins, paddings and borders."""
        return self.margin_left + self.margin_right + \
               self.padding_left + self.padding_right + \
               self.border_left_width + self.border_right_width

    def vertical_surroundings(self):
        """Sum of all vertical margins, paddings and borders."""
        return self.margin_top + self.margin_bottom + \
               self.padding_top + self.padding_bottom + \
               self.border_top_width + self.border_bottom_width

    # Corners positions

    def content_box_x(self):
        """Absolute horizontal position of the content box."""
        return self.position_x + self.margin_left + self.padding_left + \
            self.border_left_width

    def content_box_y(self):
        """Absolute vertical position of the content box."""
        return self.position_y + self.margin_top + self.padding_top + \
            self.border_top_width

    def padding_box_x(self):
        """Absolute horizontal position of the padding box."""
        return self.position_x + self.margin_left + self.border_left_width

    def padding_box_y(self):
        """Absolute vertical position of the padding box."""
        return self.position_y + self.margin_top + self.border_top_width

    def border_box_x(self):
        """Absolute horizontal position of the border box."""
        return self.position_x + self.margin_left

    def border_box_y(self):
        """Absolute vertical position of the border box."""
        return self.position_y + self.margin_top

    def reset_spacing(self, side):
        """Set to 0 the margin, padding and border of ``side``."""
        setattr(self, 'margin_%s' % side, 0)
        setattr(self, 'padding_%s' % side, 0)
        setattr(self, 'border_%s_width' % side, 0)

        self.style['margin-%s' % side] = None
        self.style['padding-%s' % side] = None
        self.style['border-%s-width' % side] = None

    # Positioning schemes

    def is_floated(self):
        """Return whether this box is floated."""
        return get_single_keyword(self.style.float) != 'none'

    def is_absolutely_positioned(self):
        """Return whether this box is in the absolute positioning scheme."""
        return get_single_keyword(self.style.position) in ('absolute', 'fixed')

    def is_in_normal_flow(self):
        """Return whether this box is in normal flow."""
        return not (self.is_floated() or self.is_absolutely_positioned())


class PageBox(Box):
    """Box for a page.

    Initially the whole document will be in a single page box. During layout
    a new page box is created after every page break.

    """

    __slots__ = ('page_number', 'root_box', 'outer_width', 'outer_height')

    def __init__(self, document, page_number):
        # starting at 1 for the first page.
        self.page_number = page_number
        # Page boxes are not linked to any element.
        super(PageBox, self).__init__(document, element=None)

    def __repr__(self):
        return '<%s %s>' % (type(self).__name__, self.page_number)

    def _init_style(self):
        """Initialize the style of the page.'"""
        # First page is a right page.
        # TODO: this "should depend on the major writing direction of the
        # document".
        first_is_right = True
        is_right = (self.page_number % 2) == (1 if first_is_right else 0)
        page_type = 'right' if is_right else 'left'
        if self.page_number == 1:
            page_type = 'first_' + page_type
        style = self.document.computed_styles['@page', page_type]
        # Copying might not be needed, but let’s be careful with mutable
        # objects.
        self.style = style.copy()

    def containing_block_size(self):
        """Get the size of the containing block."""
        return self.outer_width, self.outer_height


class ParentBox(Box):
    """A box that has children."""

    __slots__ = ()

    def __init__(self, document, element):
        super(ParentBox, self).__init__(document, element)
        self.empty()

    def empty(self):
        """Initialize or empty the children list."""
        self.children = collections.deque()

    def add_child(self, child):
        """Add the new child to the children list and set its parent."""
        child.parent = self
        self.children.append(child)

    def descendants(self):
        """A flat generator for a box, its children and descendants."""
        yield self
        for child in self.children or []:
            if hasattr(child, 'descendants'):
                for grand_child in child.descendants():
                    yield grand_child
            else:
                yield child

    def translate(self, x, y):
        """Change the position of the box.

        Also update the children’s positions accordingly.

        """
        super(ParentBox, self).translate(x, y)
        for child in self.children:
            child.translate(x, y)


class BlockLevelBox(Box):
    """A box that participates in an block formatting context.

    An element with a ``display`` value of ``block``, ``list-item`` or
    ``table`` generates a block-level box.

    """
    __slots__ = ()


class BlockContainerBox(ParentBox):
    """A box that contains only block-level boxes or only line boxes.

    A box that either contains only block-level boxes or establishes an inline
    formatting context and thus contains only line boxes.

    A non-replaced element with a ``display`` value of ``block``,
    ``list-item``, ``inline-block`` or 'table-cell' generates a block container
    box.

    """
    __slots__ = ()


class BlockBox(BlockContainerBox, BlockLevelBox):
    """A block-level box that is also a block container.

    A non-replaced element with a ``display`` value of ``block``, ``list-item``
    generates a block box.

    """
    __slots__ = ('outside_list_marker',)


class AnonymousBox(Box):
    """A box that is not directly generated by an element.

    Inherits style instead of copying them.

    """

    __slots__ = ()

    def _init_style(self):
        parent_style = self.document.style_for(self.element)
        self.style = computed_from_cascaded(self.element, {}, parent_style)

        # These properties are not inherited so they always have their initial
        # value, zero. The used value is zero too.
        self.margin_top = 0
        self.margin_bottom = 0
        self.margin_left = 0
        self.margin_right = 0

        self.padding_top = 0
        self.padding_bottom = 0
        self.padding_left = 0
        self.padding_right = 0

        self.border_top_width = 0
        self.border_bottom_width = 0
        self.border_left_width = 0
        self.border_right_width = 0


class AnonymousBlockBox(AnonymousBox, BlockBox):
    """A box that wraps inline-level boxes where block-level boxes are needed.

    Block containers (eventually) contain either only block-level boxes or only
    inline-level boxes. When they initially contain both, consecutive
    inline-level boxes are wrapped in an anonymous block box by
    :meth:`boxes.inline_in_block`.

    """
    __slots__ = ()


class LineBox(AnonymousBox, ParentBox):
    """A box that represents a line in an inline formatting context.

    Can only contain inline-level boxes.

    In early stages of building the box tree a single line box contains many
    consecutive inline boxes. Later, during layout phase, each line boxes will
    be split into multiple line boxes, one for each actual line.

    """
    __slots__ = ()


class InlineLevelBox(Box):
    """A box that participates in an inline formatting context.

    An inline-level box that is not an inline box is said to be "atomic". Such
    boxes are inline blocks, replaced elements and inline tables.

    An element with a ``display`` value of ``inline``, ``inline-table``, or
    ``inline-block`` generates an inline-level box.

    """
    __slots__ = ()


class InlineBox(InlineLevelBox, ParentBox):
    """An inline box with inline children.

    A box that participates in an inline formatting context and whose content
    also participates in that inline formatting context.

    A non-replaced element with a ``display`` value of ``inline`` generates an
    inline box.

    """
    __slots__ = ()


class TextBox(AnonymousBox, InlineLevelBox):
    """A box that contains only text and has no box children.

    Any text in the document ends up in a text box. What CSS calls "anonymous
    inline boxes" are also text boxes.

    """

    __slots__ = ('text', 'extents', 'logical_extents')

    def __init__(self, document, element, text):
        super(TextBox, self).__init__(document, element)
        self.text = text


class AtomicInlineLevelBox(InlineLevelBox):
    """An atomic box in an inline formatting context.

    This inline-level box cannot be split for line breaks.

    """
    __slots__ = ()


class InlineBlockBox(AtomicInlineLevelBox, BlockContainerBox):
    """A box that is both inline-level and a block container.

    It behaves as inline on the outside and as a block on the inside.

    A non-replaced element with a 'display' value of 'inline-block' generates
    an inline-block box.

    """
    __slots__ = ()


class ReplacedBox(Box):
    """A box whose content is replaced.

    For example, ``<img>`` are replaced: their content is rendered externally
    and is opaque from CSS’s point of view.

    """

    __slots__ = ('replacement',)

    def __init__(self, document, element, replacement):
        super(ReplacedBox, self).__init__(document, element)
        self.replacement = replacement


class BlockLevelReplacedBox(ReplacedBox, BlockLevelBox):
    """A box that is both replaced and block-level.

    A replaced element with a ``display`` value of ``block``, ``liste-item`` or
    ``table`` generates a block-level replaced box.

    """
    __slots__ = ()


class InlineLevelReplacedBox(ReplacedBox, AtomicInlineLevelBox):
    """A box that is both replaced and inline-level.

    A replaced element with a ``display`` value of ``inline``,
    ``inline-table``, or ``inline-block`` generates an inline-level replaced
    box.

    """
    __slots__ = ()


class ImageMarkerBox(InlineLevelReplacedBox, AnonymousBox):
    """A box for an image list marker.

    An element with ``display: list-item`` and a valid image for
    ``list-style-image`` generates an image list maker box.  This box is
    anonymous, inline-level, and replaced.

    """
    __slots__ = ()
