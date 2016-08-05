from __future__ import absolute_import, print_function

import logging
import six
import time
import traceback

from django.core.urlresolvers import reverse
from django.utils.safestring import mark_safe
from django.views.generic import View
from random import Random

from sentry.digests import Record
from sentry.digests.notifications import (
    Notification,
    build_digest,
)
from sentry.digests.utilities import get_digest_metadata
from sentry.http import get_server_hostname
from sentry.models import (
    Activity,
    Event,
    Group,
    OrganizationMember,
    Project,
    Rule,
    Team,
)
from sentry.plugins.sentry_mail.activity import emails
from sentry.utils.dates import to_timestamp
from sentry.utils.email import inline_css
from sentry.utils.http import absolute_uri
from sentry.utils.generators import State, generate_organization
from sentry.web.decorators import login_required
from sentry.web.helpers import render_to_response, render_to_string

logger = logging.getLogger(__name__)


def get_generator_state(request):
    seed = request.GET.get('seed', six.text_type(time.time()))
    return State(Random(seed))


# TODO(dcramer): use https://github.com/disqus/django-mailviews
class MailPreview(object):
    def __init__(self, html_template, text_template, context=None):
        self.html_template = html_template
        self.text_template = text_template
        self.context = context if context is not None else {}

    def text_body(self):
        return render_to_string(self.text_template, self.context)

    def html_body(self):
        try:
            return inline_css(render_to_string(self.html_template, self.context))
        except Exception:
            traceback.print_exc()
            raise

    def render(self, request):
        return render_to_response('sentry/debug/mail/preview.html', {
            'preview': self,
            'format': request.GET.get('format'),
        })


class ActivityMailPreview(object):
    def __init__(self, activity):
        self.email = emails.get(activity.type)(activity)

    def get_context(self):
        context = self.email.get_base_context()
        context.update(self.email.get_context())
        return context

    def text_body(self):
        return render_to_string(self.email.get_template(), self.get_context())

    def html_body(self):
        try:
            return inline_css(render_to_string(
                self.email.get_html_template(), self.get_context()))
        except Exception:
            import traceback
            traceback.print_exc()
            raise


class ActivityMailDebugView(View):
    def get(self, request):
        state = get_generator_state(request)
        generated_organization = generate_organization(state)
        generated_team = generated_organization.related[Team]()
        generated_project = generated_team.related[Project]()
        generated_group = generated_project.related[Group]()
        generated_event = generated_group.related[Event]()

        activity = Activity(
            group=generated_group.instance,
            project=generated_project.instance,
            **self.get_activity(
                request,
                generated_event.instance,
            )
        )

        return render_to_response('sentry/debug/mail/preview.html', {
            'preview': ActivityMailPreview(activity),
            'format': request.GET.get('format'),
        })


@login_required
def new_event(request):
    platform = request.GET.get('platform', None)
    state = get_generator_state(request)
    generated_organization = generate_organization(state)
    generated_team = generated_organization.related[Team]()
    generated_project = generated_team.related[Project]()
    generated_group = generated_project.related[Group]()
    generated_event = generated_group.related[Event](
        platform=platform,
    )
    generated_rule = generated_project.related[Rule]()

    interface_list = []
    for interface in six.itervalues(generated_event.instance.interfaces):
        body = interface.to_email_html(generated_event.instance)
        if not body:
            continue
        interface_list.append((interface.get_title(), mark_safe(body)))

    return MailPreview(
        html_template='sentry/emails/error.html',
        text_template='sentry/emails/error.txt',
        context={
            'rule': generated_rule.instance,
            'group': generated_group.instance,
            'event': generated_event.instance,
            'link': 'http://example.com/link',
            'interfaces': interface_list,
            'tags': generated_event.instance.get_tags(),
            'project_label': generated_project.instance.name,
            'tags': [
                ('logger', 'javascript'),
                ('environment', 'prod'),
                ('level', 'error'),
                ('device', 'Other')
            ]
        },
    ).render(request)


@login_required
def digest(request):
    state = get_generator_state(request)
    generated_organization = generate_organization(state)
    generated_team = generated_organization.related[Team]()
    generated_project = generated_team.related[Project]()
    rules = [generated_project.related[Rule]().instance for _ in range(random.randint(1, 4))]

    state = {
        'project': generated_project.instance,
        'groups': {},
        'rules': {rule.id: rule for rule in rules},
        'event_counts': {},
        'user_counts': {},
    }

    records = []

    for i in range(random.randint(1, 30)):
        generated_group = generated_project.related[Group]()
        state['groups'][generated_group.instance.id] = generated_group.instance

        for i in range(random.randint(1, 10)):
            event = generated_group.related[Event]().instance
            records.append(
                Record(
                    event.event_id,
                    Notification(
                        event,
                        random.sample(state['rules'], random.randint(1, len(state['rules']))),
                    ),
                    to_timestamp(event.datetime),
                )
            )

            state['event_counts'][generated_group.instance.id] = random.randint(10, 1e4)
            state['user_counts'][generated_group.instance.id] = random.randint(10, 1e4)

    digest = build_digest(generated_project.instance, records, state)
    start, end, counts = get_digest_metadata(digest)

    return MailPreview(
        html_template='sentry/emails/digests/body.html',
        text_template='sentry/emails/digests/body.txt',
        context={
            'project': generated_project.instance,
            'counts': counts,
            'digest': digest,
            'start': start,
            'end': end,
        },
    ).render(request)


@login_required
def request_access(request):
    state = get_generator_state(request)
    generated_organization = generate_organization(state)
    generated_team = generated_organization.related[Team]()
    return MailPreview(
        html_template='sentry/emails/request-team-access.html',
        text_template='sentry/emails/request-team-access.txt',
        context={
            'email': 'foo@example.com',
            'name': 'George Bush',
            'organization': generated_organization.instance,
            'team': generated_team.instance,
            'url': absolute_uri(reverse('sentry-organization-members', kwargs={
                'organization_slug': generated_organization.instance.slug,
            }) + '?ref=access-requests'),
        },
    ).render(request)


@login_required
def invitation(request):
    state = get_generator_state(request)
    generated_organization = generate_organization(state)
    generated_organization_member = generated_organization.related[OrganizationMember]()
    return MailPreview(
        html_template='sentry/emails/member-invite.html',
        text_template='sentry/emails/member-invite.txt',
        context={
            'email': 'foo@example.com',
            'organization': generated_organization,
            'url': absolute_uri(reverse('sentry-accept-invite', kwargs={
                'member_id': generated_organization_member.instance.id,
                'token': generated_organization_member.instance.token,
            })),
        },
    ).render(request)


@login_required
def access_approved(request):
    state = get_generator_state(request)
    generated_organization = generate_organization(state)
    generated_team = generated_organization.related[Team]()
    return MailPreview(
        html_template='sentry/emails/access-approved.html',
        text_template='sentry/emails/access-approved.txt',
        context={
            'email': 'foo@example.com',
            'name': 'George Bush',
            'organization': generated_organization.instance,
            'team': generated_team.instance,
        },
    ).render(request)


@login_required
def confirm_email(request):
    email = request.user.emails.first()
    email.set_hash()
    email.save()
    return MailPreview(
        html_template='sentry/emails/confirm_email.html',
        text_template='sentry/emails/confirm_email.txt',
        context={
            'confirm_email': 'foo@example.com',
            'user': request.user,
            'url': absolute_uri(reverse(
                'sentry-account-confirm-email',
                args=[request.user.id, email.validation_hash]
            )),
            'is_new_user': True,
        },
    ).render(request)


@login_required
def recover_account(request):
    return MailPreview(
        html_template='sentry/emails/recover_account.html',
        text_template='sentry/emails/recover_account.txt',
        context={
            'user': request.user,
            'url': absolute_uri(reverse(
                'sentry-account-confirm-email',
                args=[request.user.id, 'XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX']
            )),
            'domain': get_server_hostname(),
        },
    ).render(request)
