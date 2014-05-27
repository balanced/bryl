import re
import setuptools


install_requires = [
]

extras_require = {
    'tests': [
        'nose >=1.0,<2.0',
        'mock >=1.0,<2.0',
        'unittest2 >=0.5.1,<0.6',
        'coverage',
    ],
}

packages = setuptools.find_packages(
    '.', exclude=('tests', 'tests.*')
)

setuptools.setup(
    name='bryl',
    version=(
        re
        .compile(r".*__version__ = '(.*?)'", re.S)
        .match(open('bryl/__init__.py').read())
        .group(1)
    ),
    url='https://github.com/bninja/bryl/',
    license=open('LICENSE').read(),
    author='egon',
    author_email='egon@gb.com',
    description='.',
    long_description=open('README.rst').read(),
    packages=packages,
    package_data={'': ['LICENSE']},
    include_package_data=True,
    install_requires=install_requires,
    extras_require=extras_require,
    tests_require=extras_require['tests'],
    test_suite='nose.collector',
    classifiers=[
        'Intended Audience :: Developers',
        'Development Status :: 4 - Beta',
        'Natural Language :: English',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'License :: OSI Approved :: ISC License (ISCL)',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
    ],
)
