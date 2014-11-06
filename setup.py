import re
import setuptools.command.test


class PyTest(setuptools.command.test.test):

    def finalize_options(self):
        setuptools.command.test.test.finalize_options(self)
        self.test_args = ['tests.py']
        self.test_suite = True

    def run_tests(self):
        import pytest

        pytest.main(self.test_args)


install_requires = [
]

extras_require = {
    'tests': [
        'pytest >=2.5.2,<3',
        'pytest-cov >=1.7,<2',
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
    url='https://github.com/balanced/bryl/',
    license=open('LICENSE').read(),
    author='Balanced',
    author_email='dev+bryl@balancedpayments.com',
    description='.',
    long_description=open('README.rst').read(),
    packages=packages,
    package_data={'': ['LICENSE']},
    include_package_data=True,
    install_requires=install_requires,
    extras_require=extras_require,
    tests_require=extras_require['tests'],
    cmdclass={
        'test': PyTest,
    },
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
