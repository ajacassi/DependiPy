from setuptools import find_packages, setup


version = []
with open("DependiPy/version.py", "r") as f:
    for line in f:
        version.append(str(line.strip()))

version = version[0].split("'")[1]

argparse = 'argparse==1.4.0'
tqdm = 'tqdm==4.64.1'
pandas = 'pandas==2.0.0'
numpy = 'numpy==1.23.5'

setup(
    name='DependiPy',
    version=version,
    packages=find_packages(include=['DependiPy']),
    license='MIT',
    author='Andrea Jacassi',
    author_email='',
    description='',
    url="https://github.com/ajacassi/DependiPy.git",
    install_requires=[argparse, tqdm, pandas, numpy],
    entry_points={"console_scripts": ["DependiPy= DependiPy.librarian:main [path]"]}
)
