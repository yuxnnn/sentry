from __future__ import absolute_import

import six

from rest_framework.serializers import WritableField, ValidationError


class DictField(WritableField):
    def __init__(self, child=None, **kwargs):
        self.child = child
        super(DictField, self).__init__(**kwargs)

    def initialize(self, **kwargs):
        super(DictField, self).initialize(**kwargs)
        if self.child is not None:
            self.child.initialize(**kwargs)

    def to_native(self, obj):
        return obj

    def from_native(self, data):
        if not isinstance(data, dict):
            msg = 'Incorrect type. Expected a mapping, but got %s'
            raise ValidationError(msg % type(data).__name__)

        if self.child is None:
            return data
        return {k: self.child.from_native(v) for k, v in six.iteritems(data)}
