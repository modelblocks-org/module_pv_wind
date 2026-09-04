"""Tests to be executed locally, as they are more computationally intense."""

import subprocess


def test_europe_nuts2_onshore(user_path):
    """A larger test case for Europe at NUTS2 spatial resolution."""
    target = "results/era5_2017/Europe_NUTS2_onshore/raster_europe/capacityfactors_wind_onshore_3MW.nc"
    assert subprocess.run(
        f"snakemake --use-conda --cores 4 --configfile=tests/config_local_test.yaml {target}",
        shell=True,
        check=True,
        cwd=user_path.parent.parent,
    )
