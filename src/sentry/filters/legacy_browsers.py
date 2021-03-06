from __future__ import absolute_import

from .base import Filter

from ua_parser.user_agent_parser import Parse
from rest_framework import serializers
from sentry.models import ProjectOption
from sentry.api.fields import MultipleChoiceField

MIN_VERSIONS = {
    'Chrome': 0,
    'IE': 10,
    'Firefox': 0,
    'Safari': 6,
    'Edge': 0,
    'Opera': 15,
    'Android': 4,
}


class LegacyBrowserFilterSerializer(serializers.Serializer):
    active = serializers.BooleanField()
    subfilters = MultipleChoiceField(choices=[
        'ie_pre_9',
        'ie9',
        'opera_pre_15',
        'android_pre_4',
        'safari_pre_6'
    ])


class LegacyBrowsersFilter(Filter):
    id = 'legacy-browsers'
    name = 'Filter out known errors from legacy browsers'
    description = 'Older browsers often give less accurate information, and while they may report valid issues, the context to understand them is incorrect or missing.'
    default = False
    serializer_cls = LegacyBrowserFilterSerializer

    def is_enabled(self):
        # May be either a '1' or an iterable for new style
        # The javascript code requires this to return either
        # a boolean or a list of subfilters depending on if all, none, or some
        # legacy browsers should be filtered
        rv = ProjectOption.objects.get_value(
            project=self.project,
            key='filters:{}'.format(self.id),
            default='1' if self.default else '0',
        )

        if rv == '1':
            return True
        if rv == '0':
            return False

        return rv

    def enable(self, value=None):
        if value is None:
            value = {}

        option_val = '0'
        if 'active' in value:
            if value['active']:
                option_val = '1'
        elif 'subfilters' in value and len(value['subfilters']) > 0:
            option_val = set(value['subfilters'])

        ProjectOption.objects.set_value(
            project=self.project,
            key='filters:{}'.format(self.id),
            value=option_val,
        )

    def get_user_agent(self, data):
        try:
            for key, value in data['sentry.interfaces.Http']['headers']:
                if key.lower() == 'user-agent':
                    return value
        except LookupError:
            return ''

    def filter_default(self, browser):
        try:
            minimum_version = MIN_VERSIONS[browser['family']]
        except KeyError:
            return False

        try:
            major_browser_version = int(browser['major'])
        except (TypeError, ValueError):
            return False

        if minimum_version > major_browser_version:
            return True

        return False

    def filter_opera_pre_15(self, browser):
        if not browser['family'] == "Opera":
            return False

        try:
            major_browser_version = int(browser['major'])
        except (TypeError, ValueError):
            return False

        if major_browser_version < 15:
            return True

        return False

    def filter_safari_pre_6(self, browser):
        if not browser['family'] == "Safari":
            return False

        try:
            major_browser_version = int(browser['major'])
        except (TypeError, ValueError):
            return False

        if major_browser_version < 6:
            return True

        return False

    def filter_android_pre_4(self, browser):
        if not browser['family'] == "Android":
            return False

        try:
            major_browser_version = int(browser['major'])
        except (TypeError, ValueError):
            return False

        if major_browser_version < 4:
            return True

        return False

    def filter_ie9(self, browser):
        if not browser['family'] == "IE":
            return False

        try:
            major_browser_version = int(browser['major'])
        except (TypeError, ValueError):
            return False

        if major_browser_version == 9:
            return True

        return False

    def filter_ie_pre_9(self, browser):
        if not browser['family'] == "IE":
            return False

        try:
            major_browser_version = int(browser['major'])
        except (TypeError, ValueError):
            return False

        if major_browser_version <= 8:
            return True

        return False

    def test(self, data):
        if data.get('platform') != 'javascript':
            return False

        opts = ProjectOption.objects.get_value(
            project=self.project,
            key='filters:{}'.format(self.id),
        )

        value = self.get_user_agent(data)
        if not value:
            return False

        ua = Parse(value)
        if not ua:
            return False

        browser = ua['user_agent']

        if not browser['family']:
            return False

        # handle old style config
        if opts == '1':
            return self.filter_default(browser)

        # New style is not a simple boolean, but a list of
        # specific filters to apply
        if opts:
            for key in opts:
                try:
                    fn = getattr(self, 'filter_' + key)
                except AttributeError:
                    pass
                else:
                    if fn(browser):
                        return True

        return False
