from setuptools import setup, find_packages

setup(
    name="cloudlydev",
    version="0.1.0",
    description="A local development server for AWS Lambda",
    author="Nana Duah",
    author_email="development@forkintech.com",
    packages=find_packages("src"),
    install_requires=["pyyaml", "bottle"],
    entry_points={"console_scripts": ["cloudlydev=cloudlydev.main:main"]},
)
