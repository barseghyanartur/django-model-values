from setuptools import setup

setup(
    name='django-model-values',
    version='0.4',
    description='Taking the O out of ORM.',
    long_description=open('README.rst').read(),
    author='Aric Coady',
    author_email='aric.coady@gmail.com',
    url='https://bitbucket.org/coady/django-model-values',
    license='Apache Software License',
    py_modules=['model_values'],
    install_requires=['django>=1.8'],
    tests_require=['pytest-django', 'pytest-cov'],
    keywords='values_list pandas column-oriented data mapper pattern orm',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Framework :: Django :: 1.8',
        'Framework :: Django :: 1.10',
        'Framework :: Django :: 1.11',
        'Framework :: Django :: 2.0',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Database :: Database Engines/Servers',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
