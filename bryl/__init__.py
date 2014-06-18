"""
"""
__all__ = [
    'Field',
    'Numeric',
    'Alphanumeric',
    'Date',
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


class Field(object):

    LEFT = 'left'
    RIGHT = 'right'

    _order = itertools.count()
    pad = ''
    align = None
    offset = None
    default = None
    pattern = None
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
                '{0}.{1} value is missing'.format(type(record).__name__, self.name)
            )
        value = record[self.name]
        if value is None:
            value = self.default
        return value

    def __set__(self, record, value):
        new_value = self.handle_validation(record, value)
        if self._constant is not None:
            if self._constant != value:
                raise TypeError(
                    '{0} is constant and cannot be modified'.format(self)
                )
            return
        record[self.name] = new_value

    def fill(self, record, value):
        new_value = self.handle_validation(record, value)
        if self._constant is not None:
            return
        record[self.name] = new_value

    def handle_validation(self, record, value):
        if value is not None:
            error = self.validate(value)
            if error:
                try:
                    value = self.load(value)
                    error = self.validate(value)
                except (self.error_type, ValueError, TypeError):
                    pass
            if error:
                try:
                    value = self.load(str(value))
                    error = self.validate(value)
                except (self.error_type, ValueError, TypeError):
                    pass
            if error:
                raise self.error_type(
                    'Invalid {0}.{1} value {2} for  - {3}'
                    .format(type(record).__name__, self.name, value, error)
                )
            return value

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

    def validate(self, value):
        pass

    def error(self, value, description):
        return description

    def pack(self, value):
        error = self.validate(value)
        if error:
            raise self.error_type(
                'Invalid {0} value {1} for - {2}'.format(self, value, error)
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

    def normalize(self, value):
        if value is None:
            return self.default
        if not isinstance(value, basestring):
            raise ValueError('Must be as string')
        if self.enum and value not in self.enum:
            if value.upper() in self.enum:
                return value.upper()
            if value.lower() in self.enum:
                return value.lower()
            raise ValueError(
                'Must be one of {0}, got "{1}"'.format(self.enum, value)
            )
        value = ''.join(c for c in value if c in self.alphabet)
        if len(value) > self.length:
            value = value[:self.length]
        return value

    def validate(self, value):
        if not isinstance(value, basestring):
            return self.error(value, 'must be a string')
        if self.enum and value not in self.enum:
            return self.error(
                value, 'must be one of {0}, got "{1}"'.format(self.enum, value)
            )
        if len(value) > self.length:
            return self.error(value, 'must have length <= {0}'.format(self.length))
        for i, c in enumerate(value):
            if c not in self.alphabet:
                return self.error(
                    value, 'has invalid character "{0}" @ {1}'.format(c, i)
                )
        if self._constant is not None and value != self._constant:
            return self.error(value, 'must be constant {0}'.format(repr(self._constant)))


class Datetime(Field):

    default = None

    format_re = re.compile(
        'Y{4}|Y{2}|D{3}|D{2}|M{2}|'           # day
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
        'hh': '%H',   # 24 hr
        'HH': '%I',   # 12 hr
        'mm': '%M',
        'ss': '%S',
        'pp': '%p',   # http://stackoverflow.com/a/1759485
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
            except Field.error_type:
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

    def __init__(self, file_name, line_no, reason):
        super(Malformed, self).__init__(
            "{0} @ {1} - {2}".format(file_name, line_no, reason)
        )
        self.file_name = file_name
        self.line_no = line_no
        self.reason = reason


class Reader(collections.Iterator):

    record_type = Record

    def __init__(self, fo, include_terminal=False, expected_terminal=None):
        self.fo = fo
        self.include_terminal = include_terminal
        self.expected_terminal = expected_terminal
        self.name = getattr(self.fo, 'name', '<memory>')
        self.line_no = 1
        self.retry = None

    # collections.Iterator

    def __iter__(self):
        return self

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
                self.malformed(line_no, 'unexpected record type {0}'.format(type(record)))
            return
        return record

    def as_record(self, line, line_no):
        record_type = self.as_record_type(line, line_no)
        if inspect.isclass(record_type):
            record = record_type.load(line)
        else:
            record = record_type
        return record

    def as_record_type(self, line, line_no):
        raise NotImplementedError

    def malformed(self, line_no, reason):
        raise Malformed(self.name, line_no, reason)
