from setuptools import setup, find_packages

setup(
  name='keeper',
  version='1.0.0',
  package=['keeper'],
  include_package_data=True,
  packages=find_packages(),
  install_requires=[
    'flask',
    'requests',
    'paramiko',
    'scp',
  ],
)