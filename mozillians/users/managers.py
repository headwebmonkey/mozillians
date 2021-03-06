from django.db.models import Q, Manager
from django.db.models.query import QuerySet, ValuesQuerySet

from mozillians.groups.models import Group, Language, Skill


PRIVILEGED = 1
EMPLOYEES = 2
MOZILLIANS = 3
PUBLIC = 4
PRIVACY_CHOICES = (# (PRIVILEGED, 'Privileged'),
    # (EMPLOYEES, 'Employees'),
    (MOZILLIANS, 'Mozillians'),
    (PUBLIC, 'Public'))
PUBLIC_INDEXABLE_FIELDS = ['full_name', 'ircname', 'email']
DEFAULT_PRIVACY_FIELDS = {
    'photo': None,
    'full_name': '',
    'ircname': '',
    'email': '',
    'website': '',
    'bio': '',
    'city': '',
    'region': '',
    'country': '',
    'groups': Group.objects.none(),
    'skills': Skill.objects.none(),
    'languages': Language.objects.none(),
    'vouched_by': None,
    'date_mozillian': None,
    'timezone': ''}


class UserProfileValuesQuerySet(ValuesQuerySet):
    """Custom ValuesQuerySet to support privacy.

    Note that when you specify fields in values() you need to include
    the related privacy field in your query.

    E.g. .values('first_name', 'privacy_first_name')

    """

    def _clone(self, *args, **kwargs):
        c = super(UserProfileValuesQuerySet, self)._clone(*args, **kwargs)
        c._privacy_level = getattr(self, '_privacy_level', None)
        return c

    def iterator(self):
        # Purge any extra columns that haven't been explicitly asked for
        extra_names = self.query.extra_select.keys()
        field_names = self.field_names
        aggregate_names = self.query.aggregate_select.keys()

        names = extra_names + field_names + aggregate_names

        privacy_fields = [
            (names.index('privacy_%s' % field), names.index(field), field)
            for field in set(DEFAULT_PRIVACY_FIELDS) & set(names)]

        for row in self.query.get_compiler(self.db).results_iter():
            row = list(row)
            for levelindex, fieldindex, field in privacy_fields:
                if row[levelindex] < self._privacy_level:
                    row[fieldindex] = DEFAULT_PRIVACY_FIELDS[field]
            yield dict(zip(names, row))


class UserProfileQuerySet(QuerySet):
    """Custom QuerySet to support privacy."""

    def __init__(self, *args, **kwargs):
        self.public_q = Q()
        for field in DEFAULT_PRIVACY_FIELDS:
            key = 'privacy_%s' % field
            self.public_q |= Q(**{key: PUBLIC})

        self.public_index_q = Q()
        for field in PUBLIC_INDEXABLE_FIELDS:
            key = 'privacy_%s' % field
            if field == 'email':
                field = 'user__email'
            self.public_index_q |= (Q(**{key: PUBLIC}) & ~Q(**{field: ''}))

        return super(UserProfileQuerySet, self).__init__(*args, **kwargs)

    def privacy_level(self, level=MOZILLIANS):
        """Set privacy level for query set."""
        self._privacy_level = level
        return self.all()

    def public(self):
        """Return profiles with at least one PUBLIC field."""
        return self.filter(self.public_q)

    def vouched(self):
        """Return complete and vouched profiles."""
        return self.complete().filter(is_vouched=True)

    def complete(self):
        """Return complete profiles."""
        return self.exclude(full_name='')

    def public_indexable(self):
        """Return public indexable profiles."""
        return self.complete().filter(self.public_index_q)

    def not_public_indexable(self):
        return self.complete().exclude(self.public_index_q)

    def _clone(self, *args, **kwargs):
        """Custom _clone with privacy level propagation."""
        if kwargs.get('klass', None) == ValuesQuerySet:
            kwargs['klass'] = UserProfileValuesQuerySet
        c = super(UserProfileQuerySet, self)._clone(*args, **kwargs)
        c._privacy_level = getattr(self, '_privacy_level', None)
        return c

    def iterator(self):
        """Custom QuerySet iterator which sets privacy level in every
        object returned.

        """

        def _generator():
            self._iterator = super(UserProfileQuerySet, self).iterator()
            while True:
                obj = self._iterator.next()
                obj._privacy_level = getattr(self, '_privacy_level', None)
                yield obj
        return _generator()


class UserProfileManager(Manager):
    """Custom Manager for UserProfile."""

    use_for_related_fields = True

    def get_query_set(self):
        return UserProfileQuerySet(self.model)

    def __getattr__(self, name):
        return getattr(self.get_query_set(), name)
