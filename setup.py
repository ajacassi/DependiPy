from setuptools import find_packages, setup
import os


def read_file(filename):
    with open(os.path.join(os.path.dirname(__file__), filename)) as file:
        return file.read()


version = []
with open("DependiPy/version.py", "r") as f:
    for line in f:
        version.append(str(line.strip()))

version = version[0].split("'")[1]

# version go
numpy = 'numpy==1.26.4'
argparse = 'argparse==1.4.0'
pandas = 'pandas==2.3.2'
tqdm = 'tqdm==4.64.1'
# version end

setup(
    name='DependiPy',
    version=version,
    packages=find_packages(include=['DependiPy']),
    license='MIT',
    author='Andrea Jacassi',
    long_description=read_file('README.md'),
    long_description_content_type='text/markdown',
    author_email='',
    description='',
    url="https://github.com/ajacassi/DependiPy.git",
    install_requires=[argparse, tqdm, pandas, numpy],
    entry_points={"console_scripts": ["DependiPy= DependiPy.librarian:main [path]"]}
)
