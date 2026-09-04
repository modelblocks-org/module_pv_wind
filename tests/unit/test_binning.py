"""Tests for raster layout binning."""

import sys
from pathlib import Path

import atlite
import geopandas as gpd
import pytest
import rioxarray as rxr
from gregor.aggregate import aggregate_raster_to_polygon

# workflow/scripts is not a Python package, so expose it for direct imports.
ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "workflow" / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))

from _processing import (  # noqa: E402
    assign_to_shapes_and_aggregate,
    cf_aggregated_from_raster_layout,
)
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
    """Test assign_to_shapes_and_aggregate.

    - Total availability needs to be preserved.
    - Availability per shape needs to be preserved.
    """
    # aggregate availability directly to shapes
    availabilty_poly = aggregate_raster_to_polygon(
        availability, shapes.set_index("shape_id").geometry
    )

    availability_agg = assign_to_shapes_and_aggregate(availability, shapes, cutout)

    # compare results, aggregated by shape, with direct aggregation
    availability_agg_by_shape = availability_agg.sum(dim=["x", "y"])
    availability_agg_by_shape.name = "area_potential"
    availability_agg_by_shape = availability_agg_by_shape.to_series()

    compare = availabilty_poly.join(availability_agg_by_shape)
    compare["diff"] = abs(compare["sum"] - compare["area_potential"])

    # Total availability needs to be preserved
    tol = 1e-3
    total_diff = abs(compare["sum"].sum() - compare["area_potential"].sum())
    assert total_diff < tol

    # Availability per shape needs to be preserved
    max_diff = compare["diff"].max()
    assert max_diff < tol


# def test_bin_masks():
#     # TODO test cutout func gets correct layout/matrix
#     # TODO test matrix correctly assigns to bins:
#     # sum over bins covers each shape, like belongs_to_matrix
#     # bins are in the right order
#     # profile plots show what is expected
#     # matrix sums to availability
#     cf_mean = get_cf_mean(cutout, tech, specs)
#         tech = tech_specs["tech"]
#         specs = tech_specs["specs"]
#         specs.pop("per_unit")
#         capacity_per_sq_km = 3
#         bin_edges = None  # [0, 0.2, 0.5]
#     # bin_masks(bin, shape_id, y, x)
#     bin_masks = get_bin_masks(
#         cf_mean=cf_mean,
#         availability=availability_agg,
#         bin_edges=bin_edges,
#         mode=mode,
#         per_shape=True,
#     )


def test_get_capacity_factors(user_path, availability, shapes, tech_specs):
    """Test simple call without binning."""
    capacity_factors_binned = cf_aggregated_from_raster_layout(
        user_path / "cutouts_era5_2017.nc", availability, shapes, tech_specs
    )
    capacity_factors_binned


def test_get_capacity_factors_binned(user_path, availability, shapes, tech_specs):
    """Test binned.

    # TODO test cutout func gets correct layout/matrix.
    # TODO test get_cf_mean returns correct values.
    # TODO confirm that higher bins have better mean cf.
    # TODO validate European results against literature.
    """
    capacity_factors_binned = cf_aggregated_from_raster_layout(
        user_path / "cutouts_era5_2017.nc",
        availability,
        shapes,
        tech_specs,
        bin_edges=[0, 0.2, 0.5, 0.7, 1.0],
        mode="cf",
    )
    capacity_factors_binned
