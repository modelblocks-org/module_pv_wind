"""Backend for capacity factor calculations using atlite."""

from pathlib import Path

import atlite
import geopandas as gpd
import rasterio as rio
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


def cf_aggregated_from_raster_layout(
    path_cutout: str | Path,
    layout: xr.DataArray,
    shapes: gpd.GeoDataFrame,
    tech_specs: dict,
) -> xr.DataArray:
    """Aggregated capacity factors from a raster layout."""
    # load cutout
    cutout = atlite.Cutout(path_cutout)

    # resample layout to the resolution of the cutout
    match = (
        cutout.uniform_layout()
        .rio.write_crs(cutout.crs)
        .rio.write_transform(cutout.transform)
    )
    layout_matched = layout.squeeze(drop=True)
    layout_matched = layout_matched.rio.reproject_match(
        match, resampling=rio.enums.Resampling.sum, nodata=0
    )

    # compute capacity factors
    get_capacityfactors = getattr(cutout, tech_specs["tech"])

    capacityfactors = get_capacityfactors(
        shapes=shapes, layout=layout_matched, per_unit=True, **tech_specs["specs"]
    )

    return capacityfactors


def cf_from_point_layout(
    cutout: atlite.Cutout,
    layout: xr.DataArray,
    shapes: gpd.GeoDataFrame,
    tech_specs: dict,
) -> xr.DataArray:
    """Capacity factors from a point layout."""
    raise NotImplementedError(
        "We are planning to support capacity factors from point layout, "
        "without aggregating to shapes, but it is not implemented yet."
    )


def cf_from_raster_layout(
    cutout: atlite.Cutout,
    layout: xr.DataArray,
    shapes: gpd.GeoDataFrame,
    tech_specs: dict,
) -> xr.DataArray:
    """Capacity factors from a raster layout."""
    raise NotImplementedError(
        "We are planning to support capacity factors from raster layout, "
        "without aggregating to shapes, but it is not implemented yet."
    )
