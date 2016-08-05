from __future__ import absolute_import

import itertools
import functools
import uuid
from collections import (
    defaultdict,
    namedtuple,
)
from datetime import datetime

from django.contrib.webdesign.lorem_ipsum import WORDS
from django.utils import timezone

from sentry.constants import LOG_LEVELS
from sentry.models import (
    Event,
    Group,
    GroupStatus,
    Organization,
    OrganizationMember,
    Project,
    Team,
    Rule,
)
from sentry.utils.dates import (
    to_datetime,
    to_timestamp,
)
from sentry.utils.samples import load_data


Result = namedtuple('Result', 'instance related')

class State(object):
    def __init__(self, random, sequences=None):
        if sequences is None:
            sequences = defaultdict(
                functools.partial(itertools.count, 1),
            )

        self.random = random
        self.sequences = sequences


epoch = to_timestamp(datetime(2016, 6, 1, 0, 0, 0, tzinfo=timezone.utc))


def make_message(random, length=None):
    if length is None:
        length = int(random.weibullvariate(8, 3))
    return ' '.join(random.choice(WORDS) for _ in range(length))


def make_culprit(random):
    def make_module_path_components(min, max):
        for _ in range(random.randint(min, max)):
            yield ''.join(random.sample(WORDS, random.randint(1, int(random.paretovariate(2.2)))))

    return '{module} in {function}'.format(
        module='.'.join(make_module_path_components(1, 4)),
        function=random.choice(WORDS)
    )


def generate_event(state, group, platform=None):
    if platform is None:
        platform = 'python'

    id = next(state.sequences[Event])
    event = Event(
        id=id,
        group=group,
        project=group.project,
        event_id=uuid.UUID(int=id),
        message=make_message(state.random),
        data=load_data(platform),
        datetime=to_datetime(
            state.random.randint(
                to_timestamp(group.first_seen),
                to_timestamp(group.last_seen),
            ),
        )
    )
    return Result(event, {})


def make_group_metadata(random, group):
    return {
        'type': 'error',
        'metadata': {
            'type': '{}Error'.format(
                ''.join(word.title() for word in random.sample(WORDS, random.randint(1, 3))),
            ),
            'value': make_message(random),
        }
    }


def generate_group(state, project):
    first_seen = epoch + state.random.randint(0, 60 * 60 * 24 * 30)
    last_seen = state.random.randint(
        first_seen,
        first_seen + (60 * 60 * 24 * 30)
    )

    group = Group(
        id=next(state.sequences[Group]),
        project=project,
        culprit=make_culprit(state.random),
        level=state.random.choice(LOG_LEVELS.keys()),
        message=make_message(state.random),
        first_seen=to_datetime(first_seen),
        last_seen=to_datetime(last_seen),
        status=state.random.choice((
            GroupStatus.UNRESOLVED,
            GroupStatus.RESOLVED,
        )),
    )

    if state.random.random() < 0.8:
        group.data = make_group_metadata(state.random, group)

    return Result(group, {
        Event: functools.partial(
            generate_event,
            state,
            group,
        )
    })


def generate_rule(state, project):
    return Result(
        Rule(
            id=next(state.sequences[Rule]),
            project=project,
            label=' '.join(
                state.random.choice(WORDS) for _ in xrange(state.random.randint(3, 10))
            ).title()
        ), {}
    )


def generate_project(state, team):
    id = next(state.sequences[Project])
    project = Project(
        id=id,
        name=' '.join(
            state.random.choice(WORDS) for _ in xrange(state.random.randint(1, 3))
        ).title(),
        organization=team.organization,
        team=team,
        slug='project-{}'.format(id),
    )
    return Result(project, {
        Group: functools.partial(
            generate_group,
            state,
            project,
        ),
        Rule: functools.partial(
            generate_rule,
            state,
            project,
        ),
    })


def generate_team(state, organization):
    id = next(state.sequences[Team])
    team = Team(
        id=id,
        name=' '.join(
            state.random.choice(WORDS) for _ in xrange(state.random.randint(1, 3))
        ),
        slug='team-{}'.format(id),
        organization=organization,
    )
    return Result(team, {
        Project: functools.partial(
            generate_project,
            state,
            team,
        ),
    })


def generate_organization_member(state, organization):
    return Result(
        OrganizationMember(
            id=next(state.sequences[OrganizationMember]),
            email='{}@{}.{}'.format(
                state.random.choice(WORDS),
                state.random.choice(WORDS),
                state.random.choice(('com', 'net', 'org')),
            ),
            organization=organization,
        ),
        {},
    )


def generate_organization(state):
    id = next(state.sequences[Organization])
    organization = Organization(
        id=id,
        name=' '.join(
            state.random.choice(WORDS) for _ in xrange(state.random.randint(1, 3))
        ).title(),
        slug='organization-{}'.format(id),
    )
    return Result(organization, {
        Team: functools.partial(
            generate_team,
            state,
            organization,
        ),
        OrganizationMember: functools.partial(
            generate_organization_member,
            state,
            organization,
        ),
    })
