import pytest

import bryl


def test_reserved():
    class Record(bryl.Record):

        a = bryl.Alphanumeric(length=10)

        b = bryl.Alphanumeric(length=15).reserved()

        c = bryl.Alphanumeric(length=10, default="abc123")

    # cant't set
    r1 = Record(a="hiya")
    with pytest.raises(TypeError):
        r1.b = "nonono"

    # but will read
    raw = r1.dump()
    mangle = raw[: Record.b.offset] + "fuzzy".ljust(Record.b.length) + raw[Record.c.offset :]
    r2 = Record.load(mangle)

    # and are the same
    assert r1 == r2
