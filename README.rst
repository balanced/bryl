====
bryl
====

.. image:: https://travis-ci.org/balanced/bryl.png
   :target: https://travis-ci.org/balanced/bryl

.. image:: https://coveralls.io/repos/balanced/bryl/badge.png
   :target: https://coveralls.io/r/balanced/bryl

Declaratively defining then:

- constructing and
- serializing

fixed sized records that are composed of:

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
   assert MyRecord.load(r.dump()) == r

Some applications:

- `nacha <https://github.com/balanced/nacha/>`_
- ...

===
use
===

.. code:: bash

   $ pip install bryl

===
dev
===

.. code:: bash

   $ git clone git@github.com:balanced/bryl.git
   $ cd bryl
   $ mkvirtualenv bryl
   (bryl)$ pip install -e .[tests]
   (bryl)$ py.test

=======
release
=======

Now that all tests are passing:

- Update ``bryl.__version__`` to new ``{version}``.
- Commit that ``git commit -am "Release v{version}"``
- Tag it ``git tag -a v{version} -v  v{version}``
- Push it ``git push origin --tags``

and `travis <https://travis-ci.org/balanced/bryl>`_ will take it from there.
