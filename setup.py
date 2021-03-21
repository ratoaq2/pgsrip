#!/usr/bin/env python
# -*- coding: utf-8 -*-
import io
import os
import re

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))


def read(*parts):
    # intentionally *not* adding an encoding option to open, See:
    #   https://github.com/pypa/virtualenv/issues/201#issuecomment-3145690
    return io.open(os.path.join(here, *parts), 'r').read()


def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r'^__version__ = [\'"]([^\'"]*)[\'"]', version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError('Unable to find version string.')


# requirements
install_requires = [
    'babelfish>=0.5.5',
    'cleanit>=0.4.2',
    'click>=8.0.0a1',
    'pysrt>=1.1.2',
    'pytesseract>=0.3.7',
    'numpy>=1.20.1',
    'opencv-python>=4.5.1.48'
]
tests_require = [
    'pytest>=6.2.2',
    'pytest-cov>=2.11.1',
    'pytest-flake8>=1.0.7'
]
dev_requirements = [
    'sphinx'
]
package_data = [
]

entry_points = {
    'console_scripts': [
        'pgsrip = pgsrip.cli:pgsrip'
    ]
}

setup(name='pgsrip',
      version=find_version('pgsrip', '__init__.py'),
      license='MIT',
      description='Rip your PGS subtitles',
      long_description='{readme}\n\n{history}'.format(readme=read('README.rst'), history=read('HISTORY.rst')),
      long_description_content_type='text/markdown',
      keywords='video mkv subtitles rip srt pgs sup sub metadata movie episode tv shows series',
      url='https://github.com/ratoaq2/cleanit',
      author='Rato',
      author_email='ratoaq2@gmail.com',
      classifiers=[
          'Development Status :: 5 - Production/Stable',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: Apache Software License',
          'Operating System :: OS Independent',
          'Programming Language :: Python',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
          'Programming Language :: Python :: 3.8',
          'Programming Language :: Python :: 3.9',
          'Topic :: Software Development :: Libraries :: Python Modules',
          'Topic :: Multimedia :: Video'
      ],
      packages=find_packages(),
      package_dir={'pgsrip': 'pgsrip'},
      package_data={'pgsrip': package_data},
      # include_package_data=True,
      zip_safe=True,
      entry_points=entry_points,
      install_requires=install_requires,
      tests_require=tests_require,
      extras_require={
          'tests': tests_require,
          'dev': dev_requirements
      })
