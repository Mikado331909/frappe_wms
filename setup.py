from pathlib import Path

from setuptools import find_packages, setup

from frappe_wms import __version__ as version

ROOT = Path(__file__).parent

with (ROOT / "requirements.txt").open() as f:
    install_requires = [
        line.strip()
        for line in f.read().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

setup(
    name="frappe_wms",
    version=version,
    description="Lightweight WMS location layer for ERPNext",
    long_description=(ROOT / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    author="Crings BV",
    author_email="sales@crings.eu",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
    python_requires=">=3.10",
)
