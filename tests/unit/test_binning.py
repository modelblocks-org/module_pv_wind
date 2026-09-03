"""Tests for raster layout binning."""

import sys
from pathlib import Path

import atlite
import geopandas as gpd
import pytest
import rioxarray as rxr

# workflow/scripts is not a Python package, so expose it for direct imports.
ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "workflow" / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))

from _processing import assign_to_shapes_and_aggregate  # noqa: E402
from _utils import read_yaml  # noqa: E402


@pytest.fixture(scope="module")
def cutout(user_path):
    """Cutout for testing."""
    path_cutout = user_path / "cutouts_era5_2017.nc"
    return atlite.Cutout(path_cutout)


@pytest.fixture(scope="module")
def availability(user_path):
    """Availability for testing."""
    path_availability = user_path / "layouts_raster_europe.tif"
    return rxr.open_rasterio(path_availability).sel(band=1).drop_vars("band")


@pytest.fixture(scope="module")
def shapes(user_path):
    """Netherlands shapes for testing."""
    path_shapes = user_path / "shapes_NLD_NUTS2_onshore.parquet"
    return gpd.read_parquet(path_shapes)


@pytest.fixture(scope="module")
def tech_specs(user_path):
    """Onshore wind config for testing."""
    path_tech_specs = user_path / "tech_specs_wind_onshore_3MW.yaml"
    return read_yaml(path_tech_specs)


def test_assign_and_aggregate(cutout, availability, shapes):
    """Test asssign_to_shapes_and_aggregate.
    
    # TODO test Total availability is preserved
    # TODO test availability per shape is preserved
    # TODO reflect nan handling
    """
    availability_agg = assign_to_shapes_and_aggregate(availability, shapes, cutout)
    assert availability_agg is not None


# def test_bin_masks():
#     # TODO test cutout func gets correct layout/matrix
#     # TODO test matrix correctly assigns to bins:
#     # sum over bins covers each shape, like belongs_to_matrix
#     # bins are in the right order
#     # profile plots show what is expected
#     # matrix sums to availability
#     cf_mean = get_cf_mean(cutout, tech, specs)
        # tech = tech_specs["tech"]
        # specs = tech_specs["specs"]
        # specs.pop("per_unit")
        # capacity_per_sq_km = 3
        # bin_edges = None  # [0, 0.2, 0.5]
#     # bin_masks(bin, shape_id, y, x)
#     bin_masks = get_bin_masks(
#         cf_mean=cf_mean,
#         availability=availability_agg,
#         bin_edges=bin_edges,
#         mode=mode,
#         per_shape=True,
#     )


# def test_get_cf():
#     # TODO test cutout func gets correct layout/matrix
#     # TODO test get_cf_mean returns correct values
#     # TODO confirm that higher bins have better mean cf
#     # TODO validate European results against literature
#     # without binning works
#     get_cf(
#         availability,
#         shapes,
#         cutout,
#         tech,
#         specs,
#         bin_edges=[0, 0.2, 0.5, 0.7, 1.],
#         mode="cf",
#     )
