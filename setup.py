#!/usr/bin/env python
# vim: set et sw=4 sts=4 fileencoding=utf-8:
#
# Copyright (c) 2013 Dave Hughes <dave@waveform.org.uk>
# All rights reserved.

from __future__ import (
    #unicode_literals,
    print_function,
    absolute_import,
    division,
    )

import sys
import os
from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand
from utils import description, get_version

if not sys.version_info >= (2, 7):
    raise ValueError('This package requires Python 2.7 or above')

HERE = os.path.abspath(os.path.dirname(__file__))

# Workaround <http://www.eby-sarna.com/pipermail/peak/2010-May/003357.html>
try:
    import multiprocessing
except ImportError:
    pass

# Workaround <http://bugs.python.org/issue10945>
import codecs
try:
    codecs.lookup('mbcs')
except LookupError:
    ascii = codecs.lookup('ascii')
    func = lambda name, enc=ascii: {True: enc}.get(name=='mbcs')
    codecs.register(func)

# All meta-data is defined as global variables so that other modules can query
# it easily without having to wade through distutils nonsense
NAME         = 'currentcost'
DESCRIPTION  = 'A framework for obtaining data from a CurrentCost CC-128 electricity meter'
KEYWORDS     = ['currentcost', 'electricity', 'database']
AUTHOR       = 'Dave Hughes'
AUTHOR_EMAIL = 'dave@waveform.org.uk'
MANUFACTURER = 'waveform'
URL          = 'http://github.com/waveform80/currentcost'

REQUIRES = [
    'pyserial', # The Python serial API
    ]

EXTRA_REQUIRES = {
    }

CLASSIFIERS = [
    'Development Status :: 4 - Beta',
    'Environment :: Console',
    'Intended Audience :: System Administrators',
    'Operating System :: Microsoft :: Windows',
    'Operating System :: POSIX',
    'Operating System :: Unix',
    'Programming Language :: Python :: 2.7',
    'Programming Language :: Python :: 3.3',
    ]

ENTRY_POINTS = {
        'console_scripts': [
            'cc128d = currentcost.daemon:main',
            ],
    }

PACKAGES = [
    'currentcost',
    ]

PACKAGE_DATA = {
    }


# Add a py.test based "test" command
class PyTest(TestCommand):
    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = [
            '--cov', NAME,
            '--cov-report', 'term-missing',
            '--cov-report', 'html',
            '--cov-config', 'coverage.cfg',
            'tests',
            ]
        self.test_suite = True

    def run_tests(self):
        import pytest
        errno = pytest.main(self.test_args)
        sys.exit(errno)


def main():
    setup(
        name                 = NAME,
        version              = get_version(os.path.join(HERE, NAME, '__init__.py')),
        description          = DESCRIPTION,
        long_description     = description(os.path.join(HERE, 'README.rst')),
        classifiers          = CLASSIFIERS,
        author               = AUTHOR,
        author_email         = AUTHOR_EMAIL,
        url                  = URL,
        keywords             = ' '.join(KEYWORDS),
        packages             = PACKAGES,
        package_data         = PACKAGE_DATA,
        platforms            = 'ALL',
        install_requires     = REQUIRES,
        extras_require       = EXTRA_REQUIRES,
        zip_safe             = True,
        entry_points         = ENTRY_POINTS,
        tests_require        = ['pytest-cov', 'pytest', 'mock'],
        cmdclass             = {'test': PyTest},
        )

if __name__ == '__main__':
    main()
