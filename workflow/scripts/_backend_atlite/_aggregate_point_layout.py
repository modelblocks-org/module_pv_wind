"""Backend for capacity factor calculations using atlite."""

from pathlib import Path

import atlite
import geopandas as gpd
import xarray as xr


def cf_aggregated_from_point_layout(
    path_cutout: str | Path,
    layout: xr.DataArray,
    shapes: gpd.GeoDataFrame,
    tech_specs: dict,
) -> xr.DataArray:
    """Aggregated capacity factors from a point layout."""
    # load cutout
    cutout = atlite.Cutout(path_cutout)

    # prepare layout from list of points
    layout = layout.rename(columns={"lon": "x", "lat": "y"})
    layout = cutout.layout_from_capacity_list(layout, col="capacity")

    # compute capacity factors
    get_capacityfactors = getattr(cutout, tech_specs["tech"])

    capacityfactors = get_capacityfactors(
        shapes=shapes, layout=layout, **tech_specs["specs"]
    )

    return capacityfactors
