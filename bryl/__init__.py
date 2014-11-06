"""
Declaratively defining then:

- constructing and
- serializing

fixed sized records that are  composed of:

- typed
- fixed sized

fields. This might look e.g. like:

.. code:: python

    import datetime

    import bryl


    class MyRecord(bryl.Record):

        a = bryl.Alphanumeric(length=20)

        b = bryl.Date('YYYYMMDD')

        c = bryl.Numeric(length=10, align=bryl.Field.LEFT)

        filler = bryl.Alphanumeric(length=10).reserved()

    r = MyRecord(
        a='hello',
        b=datetime.datetime.utcnow().date(),
        c=12312,
    )
    assert isinstance(r, dict)
    print MyRecord.c.offset, MyRecord.c.length
    print
    assert MyRecord.load(r.dump()) == r

Some applications:

- `nacha <https://travis-ci.org/balanced/>`_
- ...

"""
__all__ = [
    'ctx',
    'Field',
    'Numeric',
    'Alphanumeric',
    'Date',
    'Datetime',
    'Time',
    'Record',
    'Reader',
]

__version__ = '0.1.0'

import collections
import copy
import datetime
import inspect
import itertools
import os
import re
import string
import StringIO
import threading


class Context(threading.local):

    class _Frame(dict):

        def __getattr__(self, key):
            if key in self:
                return self[key]
            raise AttributeError(
                '"{0}" object has no attribute "{1}"'
                .format(type(self).__name__, key)
            )

    class _Close(object):

        def __init__(self, func):
            self.func = func

        def __enter__(self):
            return self

        def __exit__(self, type, value, traceback):
            self.func()

    def __init__(self, **defaults):
        self.stack = [self._Frame(
            alpha_filter=False,
            alpha_truncate=False,
            alpha_upper=False,
            **defaults
        )]

    def push(self, **kwargs):
        self.stack.append(self._Frame(**kwargs))
        return self._Close(self.pop)

    def pop(self):
        self.stack.pop()

    def __call__(self, **kwargs):
        self.stack[-1].update(kwargs)
        return self

    def __getattr__(self, key):
        for frame in reversed(self.stack):
            if key in frame:
                return frame[key]
        raise AttributeError(
            '"{0}" object has no attribute "{1}"'
            .format(type(self).__name__, key)
        )


ctx = Context(sanitize=True)


class Field(object):

    LEFT = 'left'
    RIGHT = 'right'

    _order = itertools.count()

    pad = ''

    align = None

    offset = None

    default = None

    pattern = None

    ctx = ctx

    error_type = ValueError

    copy = [
        'length',
        'required',
        'pad',
        'align',
        ('order', '_order'),
        'name',
        ('constant', '_constant'),
        ('enum', '_enum'),
        'offset',
        'default',
    ]

    def  __init__(self,
                  length,
                  required=True,
                  pad=None,
                  align=None,
                  order=None,
                  name=None,
                  constant=None,
                  enum=None,
                  default=None,
                  offset=None,
        ):
        self._order = self._order.next() if order is None else order
        self.name = name
        self.length = length
        self.required = required and (default is None)
        if self.required:
            self.default = None
        else:
            self.default = self.default if default is None else default
        self.pad = self.pad if pad is None else pad
        self.align = self.align if align is None else align
        self._constant = constant
        if isinstance(enum, list):
            if not enum:
                enum = dict(enum)
            else:
                if not isinstance(enum[0], tuple):
                    enum = zip(enum, enum)
                enum = dict(enum)
        self._enum = enum
        self.enum = None
        if self._enum:
            for k, v in self._enum.iteritems():
                setattr(self, k, v)
            self.enum = self._enum.values()
        self.offset = offset

    def reserved(self):
        if type(self).default is None:
            raise TypeError(
                '{0} does not have a default and so cannot be reserved'
                .format(self)
            )
        other = copy.copy(self)
        other._constant = type(self).default
        other.default = other._constant
        return other

    def constant(self, value):
        other = copy.copy(self)
        error = self.validate(value)
        if error:
            raise self.error_type(
                'Invalid {0}.constant({1}) - {2}'.format(self, value, error)
                )
        other._constant = value
        other.default = other._constant
        return other

    def __get__(self, record, record_type=None):
        if record is None:
            return self
        if self._constant is not None:
            return self._constant
        if self.name not in record:
            if self.default is not None:
                return self.default
            raise LookupError(
                '{0}.{1} value is missing'
                .format(type(record).__name__, self.name)
            )
        value = record[self.name]
        if value is None:
            value = self.default
        return value

    def __set__(self, record, value):
        new_value = self.map(record, value)
        if self._constant is not None:
            if self._constant != value:
                raise TypeError(
                    '{0} is constant and cannot be modified'.format(self)
                )
            return
        record[self.name] = new_value

    def __copy__(self):
        kwargs = {}
        for k in self.copy:
            if isinstance(k, basestring):
                k = (k, k)
            dst, src = k
            kwargs[dst] = getattr(self, src)
        return type(self)(**kwargs)

    def __repr__(self, *args, **kwargs):
        attrs = ', '.join([
            '{0}={1}'.format(k, repr(getattr(self, k)))
            for k in ['name', 'length', 'required', 'default', 'pad', 'align']
        ])
        return '{0}({1})'.format(type(self).__name__, attrs)

    @property
    def value(self):
        if self._constant is None:
            raise TypeError('Non-constant fields do not have a value')
        return self._constant

    def fill(self, record, value):
        new_value = self.map(record, value)
        if self._constant is not None:
            return
        record[self.name] = new_value

    def map(self, record, value):
        if value is not None:
            try:
                value = self.sanitize(value)
            except (self.error_type, AttributeError, ValueError, TypeError):
                pass
            error = self.validate(value)
            if error:
                try:
                    value = self.load(value)
                    error = self.validate(value)
                except (self.error_type, AttributeError, ValueError, TypeError):
                    pass
            if error:
                try:
                    value = self.load(str(value))
                    error = self.validate(value)
                except (self.error_type, AttributeError, ValueError, TypeError):
                    pass
            if error:
                raise self.error_type(
                    'Invalid {0}.{1} value {2} for - {3}'
                    .format(type(record).__name__, self.name, value, error)
                )
            return value

    def sanitize(self, value):
        return value

    def validate(self, value):
        pass

    def error(self, value, description):
        return description

    def pack(self, value):
        error = self.validate(value)
        if error:
            if isinstance(value, str):
                value = value.decode('utf-8')
            raise self.error_type(
                u'Invalid {0} value {1} for - {2}'.format(self, value, error)
            )
        value = self.dump(value)
        if self.align == self.LEFT:
            value = value + self.pad * (self.length - len(value))
        elif self.align == self.RIGHT:
            value = (self.pad * (self.length - len(value))) + value
        else:
            value = self.pad * (self.length - len(value)) + value
        if isinstance(value, unicode):
            value = value.encode('ascii')
        return value

    def dump(self, value):
        return value

    def unpack(self, raw):
        if len(raw) < self.length:
            raise self.error_type('Length must be >= {0}'.format(self.length))
        raw = raw[:self.length]
        if self.align == self.LEFT:
            value = raw.rstrip(self.pad)
        elif self.align == self.RIGHT:
            value = raw.lstrip(self.pad)
        else:
            value = raw.strip(self.pad)
        if self.pattern and not re.match(self.pattern, value):
            raise self.error_type(
                '"{0}" does not match pattern "{1}"'.format(value, self.pattern)
                )
        try:
            value = self.load(value)
        except self.error_type, ex:
            value = ex
        if isinstance(value, Exception):
            raise self.error_type('{0} - {1}'.format(self, self.error(raw, value)))
        error = self.validate(value)
        if error:
            raise self.error_type('{0} {1} - {2}'.format(self, value, error))
        return value

    def load(self, value):
        return value

    def probe(self, io):
        if self.offset is None:
            raise TypeError('{0}.offset is None'.format(self))
        restore = io.tell()
        try:
            io.seek(self.offset, os.SEEK_CUR)
            try:
                return self.unpack(io.read(self.length))
            except self.error_type:
                return None
        finally:
            io.seek(restore, os.SEEK_SET)


class Numeric(Field):

    pad = '0'
    align = Field.RIGHT
    default = 0
    min_value = 0
    max_value = None
    copy = Field.copy + [
        'min_value',
        'min_value',
        ]

    def  __init__(self, *args, **kwargs):
        self.min_value = kwargs.pop('min_value', self.min_value)
        self.max_value = kwargs.pop('max_value', self.max_value)
        super(Numeric, self).__init__(*args, **kwargs)

    def load(self, raw):
        if not raw or raw.strip() is '':
            raw = '0'
        return int(raw)

    def dump(self, value):
        return str(value)

    def validate(self, value):
        if isinstance(value, basestring) and re.match('\d+', value):
            value = int(value)
        if not isinstance(value, (int, long)):
            return self.error(value, 'must be a whole number')
        if self.enum and value not in self.enum:
            return self.error(value, 'must be one of {0}, got "{1}"'.format(
                self.enum, value))
        if len(str(value)) > self.length:
            return self.error(value, 'must have length <= {0}'.format(self.length))
        if self.min_value is not None and self.min_value > value:
            return self.error(value, 'must be >= {0}'.format(self.min_value))
        if self.max_value is not None and self.max_value < value:
            return self.error(value, 'must be <= {0}'.format(self.min_value))
        if self._constant is not None and value != self._constant:
            return self.error(value, 'must be constant {0}'.format(repr(self._constant)))


class Alphanumeric(Field):

    pad = ' '
    align = Field.LEFT
    alphabet = string.printable
    default = ''

    def sanitize(self, value):
        v = value
        if self.ctx.alpha_filter:
            v = ''.join(c for c in value if c in self.alphabet)
        if self.ctx.alpha_truncate:
            if len(v) > self.length:
                v = v[:self.length]
        if self.ctx.alpha_upper:
            v = v.upper()
        return v

    def validate(self, value):
        if not isinstance(value, basestring):
            return self.error(value, 'must be a string')
        if self.enum and value not in self.enum:
            return self.error(
                value, 'must be one of {0}, got "{1}"'.format(self.enum, value)
            )
        if len(value) > self.length:
            return self.error(
                value, 'must have length <= {0}'.format(self.length)
            )
        for i, c in enumerate(value):
            if c not in self.alphabet:
                if c not in string.printable:
                    c = hex(ord(c))
                return self.error(
                    value, 'has invalid character "{0}" @ {1}'.format(c, i)
                )


class Datetime(Field):

    default = None

    format_re = re.compile(
        'Y{4}|Y{2}|D{3}|D{2}|M{2}|'  # day
        'h{2}|H{2}|m{2}|s{2}|X{2}|Z{3}|p{2}'  # time
    )

    format_spec = {
        # day
        'YYYY': '%Y',
        'YY': '%y',
        'DDD': '%j',
        'DD': '%d',
        'MM': '%m',
        'JJJ': '%j',

        # time
        'hh': '%H',  # 24 hr
        'HH': '%I',  # 12 hr
        'mm': '%M',
        'ss': '%S',
        'pp': '%p',  # http://stackoverflow.com/a/1759485
        'ZZZ': '%Z',  # http://stackoverflow.com/a/14763274
        }

    copy = [k for k in Field.copy if k != 'length'] + ['format']

    time_zones = {
    }

    def  __init__(self, format, *args, **kwargs):
        self.format = format
        super(Datetime, self).__init__(len(self.format), *args, **kwargs)
        self._str_format, self._tz = self._to_str_format(format)

    @classmethod
    def _to_str_format(cls, format):
        tz = None
        parts = []
        prev = 0
        for m in cls.format_re.finditer(format):
            if prev != m.start():
                parts.append(format[prev:m.start()])
            prev = m.end()
            value = m.group()
            if value == 'ZZZ':
                tz = m.start(), m.end() - m.start()
                continue
            spec = cls.format_spec[value]
            parts.append(spec)
        if prev != len(format):
            parts.append(format[prev:])
        return ''.join(parts), tz

    @classmethod
    def _extract_tz(cls, raw, spec):
        offset, length = spec
        tz = raw[offset:offset + length]
        raw = raw[:offset] + raw[offset + length:]
        return raw, tz

    @classmethod
    def _insert_tz(cls, raw, tz, spec):
        offset, length = spec
        if len(tz) != length:
            raise ValueError(
                'Timezone "{0}" length != {1}'.format(tz, length)
            )
        raw = raw[:offset] + tz + raw[offset:]
        return raw

    def validate(self, value):
        if not isinstance(value, datetime.datetime):
            return self.error(value, 'must be a datetime')

    def load(self, raw):
        tz = None
        if self._tz:
            raw, tz = self._extract_tz(raw, self._tz)
            if tz not in self.time_zones:
                raise ValueError(
                    'Unsupported time-zone "{0}", expected one of {1}'
                    .format(tz, self.time_zones.keys())
                )
            tz = self.time_zones[tz]
        value = datetime.datetime.strptime(raw, self._str_format)
        if tz:
            value = tz.localize(value)
        return value

    def dump(self, value):
        raw = value.strftime(self._str_format)
        if self._tz:
            raw = self._insert_tz(raw, value.tzname(), self._tz)
        return raw


class Date(Datetime):

    format_re = re.compile(
        'Y{4}|Y{2}|D{3}|D{2}|M{2}|J{3}'  # day
    )

    def validate(self, value):
        if not isinstance(value, datetime.date):
            return self.error(value, 'must be a date')

    def load(self, raw):
        return datetime.datetime.strptime(raw, self._str_format).date()

    def dump(self, value):
        return value.strftime(self._str_format)


class Time(Datetime):

    format_re = re.compile(
        'h{2}|H{2}|m{2}|s{2}|X{2}|Z{3}|p{2}'  # time
    )

    def validate(self, value):
        if not isinstance(value, datetime.time):
            return self.error(value, 'must be a time')

    def load(self, raw):
        return super(Time, self).load(raw).time()


class RecordMeta(type):

    def __new__(mcs, name, bases, dikt):
        cls = type.__new__(mcs, name, bases, dikt)

        # backfill field names
        for name, attr in cls.__dict__.items():
            if isinstance(attr, Field) and attr.name is None:
                attr.name = name

        # cache fields
        is_field = lambda x: (
            inspect.isdatadescriptor(x) and isinstance(x, Field)
        )
        cls.fields = [
            field if field.name in cls.__dict__ else copy.copy(field)
            for _, field in inspect.getmembers(cls, is_field)
        ]
        for field in cls.fields:
            for base in bases:
                if (not hasattr(base, field.name) or
                    not isinstance(getattr(base, field.name), Field)):
                    continue
                field._order = getattr(base, field.name)._order
        cls.fields = sorted(cls.fields, key=lambda x: x._order)

        # cache field offsets
        offset = 0
        for field in cls.fields:
            field.offset = offset
            offset += field.length

        # cache length
        cls.length = sum(field.length for field in cls.fields)

        # cache default field values
        cls._defaults = dict([
            (field.name, field.default)
            for field in cls.fields if field.default is not None
        ])

        return cls


class Record(dict):

    __metaclass__ = RecordMeta

    field_type = Field

    def __init__(self, **kwargs):
        values = copy.copy(self._defaults)
        values.update(kwargs)
        for k, v in values.iteritems():
            field = getattr(type(self), k, None)
            if not field or not isinstance(field, self.field_type):
                raise ValueError(
                    '{0} does not have field {1}'.format(type(self).__name__, k)
                )
            field.fill(self, v)

    @classmethod
    def probe(cls, io):
        if isinstance(io, basestring):
            io = StringIO.StringIO(io)
        restore = io.tell()
        try:
            try:
                return cls.load(io.read(cls.length))
            except (Field.error_type, TypeError):
                return None
        finally:
            io.seek(restore, os.SEEK_SET)

    @classmethod
    def load(cls, raw):
        values = {}
        for f in cls.fields:
            value = f.unpack(raw)
            values[f.name] = value
            raw = raw[f.length:]
        return cls(**values)

    def dump(self):
        return ''.join([f.pack(f.__get__(self)) for f in self.fields])


class Malformed(ValueError):

    def __init__(self, file_name, offset, reason):
        super(Malformed, self).__init__(
            "{0} @ {1} - {2}".format(file_name, offset, reason)
        )
        self.file_name = file_name
        self.offset = offset
        self.reason = reason


class Reader(collections.Iterator):
    """
    Record iterator.
    """

    #: Type of record handled by this reader.
    record_type = None

    #: Callable used to probe `record_type` for a persisted record.
    as_record_type = None

    def __init__(self, fo, as_record_type=None):
        """
        :param fo: File-like object from which to read `record_type` records.
        :param as_record_type:
            Callable used to determine `record_type` for a persisted record:

            .. code::

            def as_record_type(reader, data, offset):
                ...

        """
        self.fo = fo
        self.name = getattr(self.fo, 'name', '<memory>')
        self.as_record_type = as_record_type or self.as_record_type
        if self.as_record_type is None:
            raise TypeError('Must define as_record_type=')
        self.retry = None

    def next_record(self, expected_type=None, default='raise'):
        raise NotImplementedError

    def malformed(self, offset, reason):
        raise Malformed(self.name, offset, reason)

    # collections.Iterator

    def __iter__(self):
        return self


class LineReader(Reader):
    """
    Terminal delimited record iterator:

    .. code:: python

        class MyLineReader(bryl.BlockReader)

            record_type = MyRecord

            @staticmethod
            def as_record_type(reader, data, offset):
                ...

        my_records = list(MyLineReader(open('/my/records', 'rU')))

    """

    def __init__(self,
                 fo,
                 as_record_type=None,
                 include_terminal=False,
                 expected_terminal=None,
        ):
        super(LineReader, self).__init__(fo, as_record_type)
        self.line_no = 1
        self.include_terminal = include_terminal
        self.expected_terminal = expected_terminal

    # Reader

    def next_record(self, expected_type=None, default='raise'):
        line, line_no = self.next_line()
        if line is None:
            if default == 'raise':
                self.malformed(line_no, 'unexpected EOF')
            return default
        try:
            record = self.as_record(line, line_no)
        except Malformed, ex:
            self.retry = line, line_no
            raise
        except self.record_type.field_type.error_type, ex:
            self.retry = line, line_no
            self.malformed(line_no, str(ex))
        if not isinstance(record, (expected_type or self.record_type)):
            self.retry = line, line_no
            if default == 'raise':
                self.malformed(
                    line_no, 'unexpected record type {0}'.format(type(record))
                )
            return
        return record

    # collections.Iterator

    def next(self):
        line, line_no = self.next_line()
        if line is None:
            raise StopIteration()
        try:
            record = self.as_record(line, line_no)
        except self.record_type.field_type.error_type, ex:
            raise self.malformed(line_no, str(ex))
        if not self.include_terminal:
            return record
        record_terminal = line[type(record).length:]
        if (self.expected_terminal is not None and
            record_terminal != self.expected_terminal):
            self.malformed(
                line_no, 'unexpected EOL "{0}"'.format(record_terminal)
            )
        return record, record_terminal

    # internals

    def next_line(self):
        if self.retry:
            line, line_no = self.retry
            self.retry = None
        else:
            line = self.fo.readline()
            if not line:
                return None, self.line_no
            line_no = self.line_no
            self.line_no += 1
        return line, line_no

    def as_record(self, line, line_no):
        record_type = self.as_record_type(self, line, line_no)
        if inspect.isclass(record_type):
            record = record_type.load(line)
        else:
            record = record_type
        return record


class BlockReader(Reader):
    """
    Fixed-size record iterator:

    .. code:: python

        class MyBlockReader(bryl.BlockReader)

            record_type = MyRecord

            record_size = 256

            @staticmethod
            def as_record_type(reader, data, offset):
                ...

        my_records = list(MyBlockReader(open('/my/records', 'rb')))

    """

    #: Fixed size, in bytes, of all records.
    record_size = None

    def __init__(self, fo, as_record_type=None, record_size=None):
        super(BlockReader, self).__init__(fo, as_record_type)
        self.record_size = record_size or self.record_size
        self.block_offset = fo.tell()

    # Reader

    def next_record(self, expected_type=None, default='raise'):
        block, block_offset = self.next_block()
        if block is None:
            if default == 'raise':
                self.malformed(block_offset, 'unexpected EOF')
            return default
        try:
            record = self.as_record(block, block_offset)
        except Malformed, ex:
            self.retry = block, block_offset
            raise
        except self.record_type.field_type.error_type, ex:
            self.retry = block, block_offset
            self.malformed(block_offset, str(ex))
        if not isinstance(record, (expected_type or self.record_type)):
            self.retry = block, block_offset
            if default == 'raise':
                self.malformed(
                    block_offset,
                    'unexpected record type {0}'.format(type(record)),
                )
            return
        return record

    # collections.Iterator

    def next(self):
        block, block_offset = self.next_block()
        if block is None:
            raise StopIteration()
        try:
            record = self.as_record(block, block_offset)
        except self.record_type.field_type.error_type, ex:
            raise self.malformed(block_offset, str(ex))
        return record

    # internals

    def next_block(self):
        if self.retry:
            block, block_offset = self.retry
            self.retry = None
        else:
            block = self.fo.read(self.record_size)
            if not block:
                return None, self.block_offset
            block_offset = self.block_offset
            self.block_offset = self.fo.tell()
        return block, block_offset

    def as_record(self, block, block_offset):
        record_type = self.as_record_type(self, block, block_offset)
        if inspect.isclass(record_type):
            record = record_type.load(block)
        else:
            record = record_type
        return record
