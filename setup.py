# setup.py
from setuptools import setup, find_packages

setup(
    name="readme-generator",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "openai",
        "click",
        "tiktoken",
    ],
    entry_points={
        "console_scripts": [
            "readme-generator = readme_generator.cli:main",
        ],
    },
    description="A CLI tool that uses AI to analyze a codebase and generate a README.",
    author="ArchZion",
    url="https://github.com/ArchZion/readme-generator",
)
