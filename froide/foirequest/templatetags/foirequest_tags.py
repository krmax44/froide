# -*- encoding: utf-8 -*-
from __future__ import unicode_literals

from difflib import SequenceMatcher
import re

from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape
from django.template.defaultfilters import urlizetrunc
from django.utils.translation import ugettext_lazy as _

from froide.helper.text_utils import unescape, split_text_by_separator

from ..models import FoiRequest
from ..foi_mail import get_alternative_mail
from ..auth import (
    can_read_foirequest, can_write_foirequest, can_read_foirequest_anonymous
)

register = template.Library()


def highlight_request(message):
    content = unescape(message.get_content().replace("\r\n", "\n"))
    description = message.request.description
    description = description.replace("\r\n", "\n")
    try:
        index = content.index(description)
    except ValueError:
        return content
    offset = index + len(description)
    return mark_safe('<div>%s</div><div class="highlight">%s</div><div class="collapse" id="letter_end">%s</div>' % (
            escape(content[:index]),
            urlizetrunc(escape(description), 40),
            escape(content[offset:]))
    )


ONLY_SPACE_LINE = re.compile('^[ \u00A0]+$', re.U | re.M)


def remove_space_lines(content):
    return ONLY_SPACE_LINE.sub('', content)


def mark_differences(content_a, content_b,
        start_tag='<span{attrs}> ',
        end_tag=' </span>',
        attrs=None,
        min_part_len=3):
    if attrs is None:
        attrs = ' class="redacted"'
    start_tag = start_tag.format(attrs=attrs)
    opened = False
    redact = False
    new_content = []
    matcher = SequenceMatcher(None, content_a, content_b)
    last_start_tag = None

    full_tag_check = lambda content, last_start_tag: \
        [x for x in content[(last_start_tag + 1):] if x.strip()]

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        long_enough = i2 - i1 > min_part_len
        redact = tag != 'equal'
        if not redact and opened and long_enough:
            if full_tag_check(new_content, last_start_tag):
                new_content.append(end_tag)
            else:
                new_content = new_content[:last_start_tag]
            opened = False
        if not opened and redact:
            opened = True
            last_start_tag = len(new_content)
            new_content.append(start_tag)
        new_content.append(escape(remove_space_lines(content_a[i1:i2])))
    if opened:
        if full_tag_check(new_content, last_start_tag):
            new_content.append(end_tag)
        else:
            new_content = new_content[:last_start_tag]

    return mark_safe(''.join(new_content))


def redact_message(message, request):
    real_content = message.get_real_content().replace("\r\n", "\n")
    redacted_content = message.get_content().replace("\r\n", "\n")

    c_1, c_2 = split_text_by_separator(real_content)
    r_1, r_2 = split_text_by_separator(redacted_content)

    foirequest = message.request
    authenticated_read = (
        can_write_foirequest(foirequest, request) or
        can_read_foirequest_anonymous(foirequest, request)
    )

    if authenticated_read:
        content_1 = mark_differences(c_1, r_1,
            attrs=' class="redacted redacted-hover"'
            ' data-toggle="tooltip" title="{title}"'.format(
                title=_('Only visible to you')
            ))
        content_2 = mark_differences(c_2, r_2,
            attrs=' class="redacted redacted-hover"'
            ' data-toggle="tooltip" title="{title}"'.format(
                title=_('Only visible to you')
            ))
    else:
        content_1 = mark_differences(r_1, c_1)
        content_2 = mark_differences(r_2, c_2)

    content_1 = urlizetrunc(content_1, 40, autoescape=False)
    content_2 = urlizetrunc(content_2, 40, autoescape=False)

    if content_2:
        return mark_safe(''.join([
            content_1,
            ('<a href="#message-footer-{message_id}" data-toggle="collapse" '
            ' aria-expanded="false" aria-controls="collapseExample">…</a>'
            '<div id="message-footer-{message_id}" class="collapse">'
            .format(message_id=message.id)),
            content_2,
            '</div>'
        ]))

    return mark_safe(content_1)


def check_same_request(context, foirequest, user, var_name):
    if foirequest.same_as_id:
        foirequest_id = foirequest.same_as_id
    else:
        foirequest_id = foirequest.id
    same_requests = FoiRequest.objects.filter(
        user=user, same_as_id=foirequest_id
    )
    if same_requests:
        context[var_name] = same_requests[0]
    else:
        context[var_name] = False
    return ""


@register.filter(name='can_read_foirequest')
def can_read_foirequest_filter(foirequest, request):
    return can_read_foirequest(foirequest, request)


@register.filter(name='can_write_foirequest')
def can_write_foirequest_filter(foirequest, request):
    return can_write_foirequest(foirequest, request)


@register.filter(name='can_read_foirequest_anonymous')
def can_read_foirequest_anonymous_filter(foirequest, request):
    return can_read_foirequest_anonymous(foirequest, request)


def alternative_address(foirequest):
    return get_alternative_mail(foirequest)


register.simple_tag(highlight_request)
register.simple_tag(redact_message)
register.simple_tag(alternative_address)
register.simple_tag(takes_context=True)(check_same_request)
