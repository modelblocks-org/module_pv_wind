"""Shared test fixtures."""

import shutil
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

import pytest


TEST_FILES = {
    "EUROPE_S_C1_ADM1.parquet": "https://zenodo.org/records/20765043/files/EUROPE_S_C1_ADM1.parquet?download=1",
    "EUROPE_L_C34_ADM1.parquet": "https://zenodo.org/records/20765043/files/EUROPE_L_C34_ADM1.parquet?download=1",
    "module_pv_wind_files.zip": "https://surfdrive.surf.nl/public.php/dav/files/fdJgBEaqz58KE3H/?accept=zip",
}


@pytest.fixture(scope="session")
def user_path() -> Path:
    """Download and unzip test files."""
    user_dir = Path("resources/user/")
    # If test suite has been downloaded, assume everything is OK.
    # Otherwise, re-download.
    for name, file_url in TEST_FILES.items():
        file_path = user_dir / name

        if not file_path.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)
            urlretrieve(file_url, file_path)

        if file_path.suffix == ".zip":
            with zipfile.ZipFile(file_path, "r") as zfile:
                zfile.extractall(file_path.parent)

    return user_dir
