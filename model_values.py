import collections
import itertools
import operator
from django.db import models
from django.utils import six
map = six.moves.map

__version__ = '0.2'

try:
    _iterable_classes = models.query.FlatValuesListIterable, models.query.ValuesListIterable
except AttributeError:  # django < 1.9
    _iterable_classes = ()


def update_wrapper(wrapper, wrapped):
    wrapper.__name__ = wrapper.__doc__ = getattr(wrapped, '__name__', wrapped)
    return wrapper


def method(lookup):
    return update_wrapper(lambda self, value: self.__eq__(value, '__' + lookup), lookup)


class Lookup(object):
    """Mixin for field lookups."""
    __ne__ = method('ne')
    __lt__ = method('lt')
    __le__ = method('lte')
    __gt__ = method('gt')
    __ge__ = method('gte')
    iexact = method('iexact')
    contains = method('contains')  # __contains__ coerces to a bool
    icontains = method('icontains')
    startswith = method('startswith')
    istartswith = method('istartswith')
    endswith = method('endswith')
    iendswith = method('iendswith')
    search = method('search')
    regex = method('regex')
    iregex = method('iregex')

    def in_(self, *values):
        """in"""
        return self.__eq__(values, '__in')

    def range(self, *values):
        """range"""
        return self.__eq__(values, '__range')


def method(func):
    return update_wrapper(lambda *args, **extra: func(*args, **extra), func)


class FExpr(models.F, Lookup):
    """Singleton for creating ``F``, ``Q``, ``Func``, and ``OrderBy`` objects with expressions.

    ``F.user.created`` == ``F('user__created')``

    ``F.user.created >= ...`` == ``Q(user__created__gte=...)``

    ``F.user.created.min()`` == ``Min('user__created')``

    ``-F.user.created`` == ``F('user__created').desc()``

    ``F.text.iexact(...)`` == ``Q(text__iexact=...)``
    """
    __neg__ = models.F.desc
    min = method(models.Min)
    max = method(models.Max)
    sum = method(models.Sum)
    mean = method(models.Avg)
    count = method(models.Count)
    var = method(models.Variance)
    std = method(models.StdDev)

    def __getattr__(self, name):
        """Return new `F`_ object with chained attribute."""
        return type(self)('{}__{}'.format(self.name, name).lstrip('_'))

    def __eq__(self, value, lookup=''):
        """Return ``Q`` object with lookup."""
        return models.Q(**{self.name + lookup: value})
F = FExpr('')


def method(func):
    return update_wrapper(lambda self: self.reduce(func), func)


class QuerySet(models.QuerySet, Lookup):
    min = method(models.Min)
    max = method(models.Max)
    sum = method(models.Sum)
    mean = method(models.Avg)
    var = method(models.Variance)
    std = method(models.StdDev)

    @property
    def _flat(self):
        if _iterable_classes:
            return issubclass(self._iterable_class, _iterable_classes[0])
        return getattr(self, 'flat', None)

    @_flat.setter
    def _flat(self, value):
        if not _iterable_classes:
            self.flat = bool(value)
        elif issubclass(self._iterable_class, _iterable_classes):
            self._iterable_class = _iterable_classes[not value]

    def __getitem__(self, key):
        """Allow column access by field names (or ``F`` objects) and filtering by ``Q`` objects.

        ``qs[field]`` returns flat ``values_list``

        ``qs[field, ...]`` returns tupled ``values_list``

        ``qs[Q_obj]`` returns filtered `QuerySet`_
        """
        if isinstance(key, tuple):
            fields = (field.name if isinstance(field, models.F) else field for field in key)
            return self.values_list(*fields)
        if isinstance(key, six.string_types):
            return self.values_list(key, flat=True)
        if isinstance(key, models.F):
            return self.values_list(key.name, flat=True)
        if isinstance(key, models.Q):
            return self.filter(key)
        return super(QuerySet, self).__getitem__(key)

    def __setitem__(self, key, value):
        """Update a single column."""
        self.update(**{key: value})

    def __eq__(self, value, lookup=''):
        """Return `QuerySet`_ filtered by comparison to given value."""
        lookups = (field + lookup for field in self._fields)
        return self.filter(**dict.fromkeys(lookups, value))

    def __contains__(self, value):
        """Return whether value is present using ``exists``."""
        if self._result_cache is None and self._flat:
            return (self == value).exists()
        return value in iter(self)

    @property
    def F(self):
        return models.F(*self._fields)

    def __add__(self, value):
        """F + value."""
        return self.F + value

    def __sub__(self, value):
        """F - value."""
        return self.F - value

    def __mul__(self, value):
        """F * value."""
        return self.F * value

    def __truediv__(self, value):
        """F / value."""
        return self.F / value
    __div__ = __truediv__

    def __mod__(self, value):
        """F % value."""
        return self.F % value

    def __pow__(self, value):
        """F ** value."""
        return self.F ** value

    def __iter__(self):
        if not hasattr(self, '_groupby'):
            return super(QuerySet, self).__iter__()
        size = len(self._groupby)
        rows = self[self._groupby + self._fields].order_by(*self._groupby).iterator()
        groups = itertools.groupby(rows, key=operator.itemgetter(*range(size)))
        Values = collections.namedtuple('Values', self._fields)
        getter = operator.itemgetter(size) if self._flat else lambda tup: Values(*tup[size:])
        return ((key, map(getter, values)) for key, values in groups)

    def groupby(self, *fields):
        """Return a grouped `QuerySet`_.

        The queryset is iterable in the same manner as ``itertools.groupby``.
        Additionally the ``reduce`` functions will return annotated querysets.
        """
        qs = self.all()
        qs._groupby = fields
        return qs

    def annotate(self, *args, **kwargs):
        qs = super(QuerySet, self).annotate(*args, **kwargs)
        if args or kwargs:
            qs._flat = False
        return qs

    def value_counts(self):
        """Return annotated value counts."""
        return self.annotate(models.Count(self._fields[0]))

    def reduce(self, *funcs):
        """Return aggregated values, or an annotated `QuerySet`_ if ``groupby`` is in use.

        :param funcs: aggregation function classes
        """
        funcs = [func(field) for field, func in zip(self._fields, itertools.cycle(funcs))]
        if hasattr(self, '_groupby'):
            return self[self._groupby].annotate(*funcs)
        names = (func.default_alias for func in funcs)
        values = collections.namedtuple('Values', names)(**self.aggregate(*funcs))
        return values[0] if self._flat else values

    def modify(self, defaults=(), **kwargs):
        """Update and return number of rows that actually changed.

        For triggering on-change logic without fetching first.

        ``if qs.modify(status=...):`` status actually changed

        ``qs.modify({'last_modified': now}, status=...)`` last_modified only updated if status updated

        :param defaults: optional mapping which will be updated conditionally, as with ``update_or_create``.
        """
        return self.exclude(**kwargs).update(**dict(defaults, **kwargs))

    def remove(self):
        """Equivalent to ``_raw_delete``, and returns number of rows deleted.

        Django's delete may fetch ids first;  this will execute only one query.
        """
        query = models.sql.DeleteQuery(self.model)
        query.get_initial_alias()
        query.where = self.query.where
        return query.get_compiler(self.db).execute_sql(models.sql.constants.CURSOR).rowcount

    def exists(self, count=1):
        """Return whether there are at least the specified number of rows."""
        if self._result_cache is None and count != 1:
            return len(self['pk'][:count]) >= count
        return super(QuerySet, self).exists()


class NotEqual(models.Lookup):
    """Missing != operator."""
    lookup_name = 'ne'

    def as_sql(self, *args):
        lhs, lhs_params = self.process_lhs(*args)
        rhs, rhs_params = self.process_rhs(*args)
        return '{} <> {}'.format(lhs, rhs), lhs_params + rhs_params

models.Field.register_lookup(NotEqual)


class Query(models.sql.Query):
    """Allow __ne=None lookup."""
    def prepare_lookup_value(self, value, lookups, *args):
        if value is None and lookups[-1:] == ['ne']:
            value, lookups[-1] = False, 'isnull'
        return super(Query, self).prepare_lookup_value(value, lookups, *args)


class Manager(models.Manager):
    def get_queryset(self):
        return QuerySet(self.model, Query(self.model), self._db, self._hints)

    def __getitem__(self, pk):
        """Return `QuerySet`_ which matches primary key.

        To encourage direct db access, instead of always using get and save.
        """
        return self.filter(pk=pk)

    def __delitem__(self, pk):
        """Delete row with primary key."""
        self[pk].delete()

    def __contains__(self, pk):
        """Return whether pk is present using ``exists``."""
        return self[pk].exists()

    def changed(self, pk, **kwargs):
        """Return mapping of fields and values which differ in the db.

        Also efficient enough to be used in boolean contexts, instead of ``exists``.
        """
        row = self[pk].exclude(**kwargs).values(*kwargs).first() or {}
        return {field: value for field, value in row.items() if value != kwargs[field]}

    def update_rows(self, data):
        """Perform bulk row updates as efficiently and minimally as possible.

        At the expense of a single select query,
        this is effective if the percentage of changed rows is relatively small.

        :param data: ``{pk: {field: value, ...}, ...}``
        :returns: set of changed pks
        """
        fields = set(itertools.chain.from_iterable(data.values()))
        rows = self.filter(pk__in=data).values('pk', *fields).iterator()
        changed = {row['pk'] for row in rows if any(row[field] != value for field, value in data[row['pk']].items())}
        for pk in changed:
            self[pk].update(**data[pk])
        return changed

    def update_columns(self, field, data):
        """Perform bulk column updates for one field as efficiently and minimally as possible.

        Faster than row updates if the number of possible values is limited, e.g., booleans.

        :param data: ``{pk: value, ...}``
        :returns: number of rows matched per value
        """
        updates = collections.defaultdict(list)
        for pk in data:
            updates[data[pk]].append(pk)
        for value in updates:
            self.filter(pk__in=updates[value])[field] = value
        return {value: len(updates[value]) for value in updates}


class classproperty(property):
    """A property bound to a class."""
    def __get__(self, instance, owner):
        return self.fget(owner)
