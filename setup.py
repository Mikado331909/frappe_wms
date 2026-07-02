from setuptools import find_packages, setup

from frappe_wms import __version__ as version

with open("requirements.txt") as f:
    install_requires = [
        line.strip()
        for line in f.read().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

setup(
    name="frappe_wms",
    version=version,
    description="Lightweight WMS location layer for ERPNext",
    author="Crings BV",
    author_email="sales@crings.eu",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
