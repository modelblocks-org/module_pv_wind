import time
from pathlib import Path

import atlite
import geopandas as gpd
import numpy as np
import xarray as xr
from gregor.disaggregate import get_belongs_to_matrix
from rasterio.features import rasterize


def cf_aggregated_from_raster_layout(
    path_cutout: str | Path,
    layout: xr.DataArray,
    shapes: gpd.GeoDataFrame,
    tech_specs: dict,
    bin_edges: list = None,
    mode="cf",
) -> xr.DataArray:
    """Aggregated capacity factors from a raster layout."""
    # load cutout
    cutout = atlite.Cutout(path_cutout)
    tech = tech_specs["tech"]
    specs = tech_specs["specs"]

    # assign layout to shapes and cutout cells, then aggregate
    # layout_agg(shape_id, y, x)
    layout_agg = assign_to_shapes_and_aggregate(layout, shapes, cutout)

    # calculate cf_mean(y, x)
    cf_mean = get_cf_mean(cutout, tech, specs)

    if bin_edges is not None:
        # If bin_edges are defined, bin the layout
        # according to the mean capacity factor
        # create the bin_masks(bin, shape_id, y, x)
        bin_masks = get_bin_masks(
            cf_mean=cf_mean,
            availability=layout_agg,
            bin_edges=bin_edges,
            mode=mode,
            per_shape=True,
        )

        # combine layout and bin_masks
        # matrix(bin, shape_id, y, x) =
        #   layout_agg(shape_id, y, x)
        #   * bin_masks(bin, shape_id, y, x)
        matrix = (layout_agg * bin_masks).transpose("bin", "shape_id", "y", "x")
        matrix = matrix.stack(shape_bin=["shape_id", "bin"], spatial=["y", "x"])
        index = matrix.indexes["bin"]

    else:
        # Don't bin if no bin_edges are given
        # matrix(shape_id, y, x) = availability_agg(shape_id, y, x)
        matrix = layout_agg.transpose("shape_id", "y", "x")
        matrix = matrix.stack(spatial=["y", "x"])
        index = matrix.indexes["shape_id"]

    capacity_factors = getattr(cutout, tech)(
        matrix=matrix,
        index=index,
        per_unit=True,
        return_capacity=False,
        # dask_kwargs=dask_kwargs,
        **specs,
    )
    capacity_factors = capacity_factors.unstack()

    return capacity_factors, cf_mean, matrix


def get_belongs_to_matrix(
    raster: xr.DataArray, polygons: gpd.GeoSeries, nodata: int = -1
) -> xr.DataArray:
    r"""Get a matrix which indicates which polygon each raster point belongs to.

    Parameters
    ----------
    raster : xr.DataArray
        Raster array to get the matrix for.
    polygons : gpd.GeoSeries
        Polygons to compute the matrix for.
    nodata : int
        Value to use as NaN, i.e. for pixels that do not belong to any polygon.

    Returns:
    -------
    xr.DataArray
        Matrix which indicates which polygon each raster point belongs to.
    """
    # TODO: fix dangerous reliance on the order in get_belongs_to_matrix.
    # TODO: Document that partial membership is not supported, which is ok if grid is fine compared to polygons
    assert len(raster.dims) == 2, "Raster data should have 2 dimensions."

    # shapes = [(geom, i) for i, geom in enumerate(polygons)]
    shapes = polygons.reset_index(drop=True)
    shapes = [(geom, i) for i, geom in shapes.items()]
    arr = rasterize(
        shapes,
        out_shape=raster.shape,
        transform=raster.rio.transform(),
        fill=nodata,  # fills invalid cases
        dtype="int32",
    )

    return xr.DataArray(arr, coords=raster.coords, dims=raster.dims)


def assign_to_shapes_and_aggregate_old(availability, shapes, cutout):
    """Assigns each pixel of the availability raster to a shape and grid cell and then aggregates.

    Usually, the availability raster has a higher spatial resolution than the cutout grid.
    Therefore, downsampling to the cutout grid and aggregating would lead to different results than
    first assigning shapes and grid cells, then aggregating.
    """
    time_0 = time.time()
    # TODO How to handle points outside any shape? When to prune?
    # TODO How to handle half- or non-overlapping availability, shapes, cutout?
    # TODO apparently, y coordinates are swapped, ranging from low to high in the output.
    # Treat shapes as the source of truth.
    # Complain if not all shapes are covered by availability and shapes
    # dump all availability outside shapes.
    _nan = "None"
    _margin = 1

    # reproject to availability's crs
    crs = availability.rio.crs
    shapes_reprojected = shapes.to_crs(crs)
    grid_reprojected = cutout.grid.to_crs(crs)

    # clip availability to the bounds of the shapes
    minx, miny, maxx, maxy = shapes.total_bounds + [
        -_margin,
        -_margin,
        _margin,
        _margin,
    ]
    # grid_reprojected_clipped = grid_reprojected.rio.clip_box()
    availability_clipped = availability.rio.clip_box(
        minx=minx, miny=miny, maxx=maxx, maxy=maxy
    )
    print("time taken til clipped:", time.time() - time_0)

    # # assign new coordinates that tell to which shape and grid cell each pixel belongs to.
    belongs_to = get_belongs_to_matrix(
        availability_clipped, shapes_reprojected.set_index("shape_id").geometry
    )
    belongs_to_grid = get_belongs_to_matrix(
        availability_clipped, grid_reprojected.geometry
    )
    data_n = availability_clipped.assign_coords(shape_number=belongs_to)
    data_n = data_n.assign_coords(cell_number=belongs_to_grid)

    # aggregate to shape_number and cell_number
    res = (
        data_n.stack(cell=("x", "y"))
        .set_index(cell=["shape_number", "cell_number"])
        .groupby("cell")
        .sum()
        .unstack("cell")
    )
    print("time taken till aggregated:", time.time() - time_0)

    # # map shape_number to shape_id and cell_number to the cells' x and y.
    shape_id = xr.DataArray(
        [
            shapes_reprojected.reset_index()["shape_id"].get(i, _nan)
            for i in res.coords["shape_number"].values
        ],
        dims="shape_number",
    )
    x_cell = xr.DataArray(
        [grid_reprojected["x"].get(i) for i in res.coords["cell_number"].values],
        dims="cell_number",
    ).astype(np.float32)
    y_cell = xr.DataArray(
        [grid_reprojected["y"].get(i) for i in res.coords["cell_number"].values],
        dims="cell_number",
    ).astype(np.float32)

    # map back to shape_id, x, y coordinates.
    res = (
        res.assign_coords(shape_id=shape_id, y=y_cell, x=x_cell)
        .set_index(cell_number=["y", "x"], shape_number="shape_id")
        .unstack("cell_number")
        .rename(shape_number="shape_id")
    )
    print("time taken till mapped:", time.time() - time_0)

    # drop shapes that do not have any availability
    res = res.where(res.shape_id != _nan, drop=True)

    print("time taken:", time.time() - time_0)

    return res


def assign_to_shapes_and_aggregate(availability, shapes, cutout):
    """Assign each pixel of availability to a shape and cutout grid cell and aggregates.

    The availability raster is not resampled before aggregation.

    Returns:
    -------
    xarray.DataArray
        Aggregated availability with dimensions ("shape_id", "y_cutout", "x_cutout").
    """
    t0 = time.perf_counter()

    margin = 1

    # reproject to common crs
    crs = availability.rio.crs
    shapes_reprojected = shapes.to_crs(crs)
    grid_reprojected = cutout.grid.to_crs(crs)

    # clip availability to shapes
    minx, miny, maxx, maxy = shapes_reprojected.total_bounds + np.array(
        [-margin, -margin, margin, margin]
    )

    availability_clipped = availability.rio.clip_box(
        minx=minx, miny=miny, maxx=maxx, maxy=maxy
    )

    print("clipped:", time.perf_counter() - t0)

    # assign every availability pixel to a shape
    shape_number = get_belongs_to_matrix(
        availability_clipped, shapes_reprojected.set_index("shape_id").geometry
    )

    print("shape rasterized:", time.perf_counter() - t0)

    # assign every availability pixel to a cutout grid cell
    cell_number = get_belongs_to_matrix(availability_clipped, grid_reprojected.geometry)

    print("grid rasterized:", time.perf_counter() - t0)

    # aggregate availability by shape and grid cell
    values = availability_clipped.values

    n_shapes = len(shapes_reprojected)
    n_cells = len(grid_reprojected)

    # flatten once
    values = values.ravel()
    shape_number = np.asarray(shape_number).ravel()
    cell_number = np.asarray(cell_number).ravel()

    # ignore pixels which aren't assigned to either a shape or cell.
    valid = (shape_number >= 0) & (cell_number >= 0) & np.isfinite(values)

    shape_number = shape_number[valid].astype(np.int64, copy=False)
    cell_number = cell_number[valid].astype(np.int64, copy=False)
    values = values[valid]

    # Map (shape_number, cell_number) -> one integer.
    #
    #     group = shape * n_cells + cell
    #
    # This gives every shape/cell combination a unique integer.
    group_number = shape_number * n_cells + cell_number

    aggregated = np.bincount(group_number, weights=values, minlength=n_shapes * n_cells)

    aggregated = aggregated.reshape(n_shapes, n_cells)

    print("aggregated:", time.perf_counter() - t0)

    # construct output
    shape_ids = shapes_reprojected["shape_id"].to_numpy()
    grid_x = grid_reprojected["x"].to_numpy()
    grid_y = grid_reprojected["y"].to_numpy()

    result = xr.DataArray(
        aggregated,
        dims=("shape_id", "cell"),
        coords={
            "shape_id": shape_ids,
            "cell": np.arange(n_cells),
            "x": ("cell", grid_x),
            "y": ("cell", grid_y),
        },
        name=availability.name,
        attrs=availability.attrs,
    )

    result = result.set_index(cell=("y", "x")).unstack("cell")
    print("result constructed:", time.perf_counter() - t0)

    return result


def get_cf_mean(cutout, tech, specs):
    """Get mean capacity factors.

    Parameters:
    -----------
    cutout: atlite.Cutout
    tech: str
        technology name
    specs: dict
        Technology specifications

    Returns:
    --------
    cf_mean: xarray.DataArray
        Mean capacity factors
    """
    time_start = time.time()

    # compute mean capacity factor,
    # as a measure of the resource quality.
    # TODO: clip to shapes before computing
    cf_mean = getattr(cutout, tech)(aggregate_time="mean", **specs)
    print(f"Computed mean capacity factor in {time.time() - time_start:.2f} seconds.")
    return cf_mean


def get_bin_masks(cf_mean, availability, bin_edges, mode="cf", per_shape=False):
    """Create masks assigning grid cells to capacity-factor bins.

    Parameters
    ----------
    cf_mean : xarray.DataArray
        Mean capacity factor with dimensions ("y", "x").

    availability : xarray.DataArray
        Available area with dimensions ("shape_id", "y", "x").

    bin_edges : sequence of float
        Bin boundaries in [0, 1].

        For ``mode="cf"``, these are fractions of the CF range.

        For ``mode="availability"``, these are availability-weighted
        percentiles of CF.

    mode : {"cf", "availability"}
        Method used to determine the actual CF boundaries.

    per_shape : bool
        If True, calculate boundaries independently for each shape.

    Returns:
    -------
    xarray.DataArray
        Boolean mask with dimensions:

        - (bin, y, x) if per_shape=False
        - (bin, shape_id, y, x) if per_shape=True
    """
    # define the  bins
    if bin_edges is None:
        bin_edges = [(0.0, 1.0)]
    else:
        bin_edges = sorted(set(bin_edges) | {0.0, 1.0})

        if not all(0.0 <= edge <= 1.0 for edge in bin_edges):
            raise ValueError("bin_edges must be between 0 and 1.")

    print(f"Using bin edges: {bin_edges}")
    bin_edges = np.asarray(bin_edges, dtype=float)

    # n_bins = len(bin_edges) - 1
    # if n_bins == 1:
    #     # create a mask without computing cf.
    #     return xr.DataArray(
    #         np.ones((1, cutout.shape[1], cutout.shape[0]), dtype=bool),
    #         dims=("bin", "y", "x"),
    #         coords={"bin": [0]},
    #     )

    if mode != "cf":
        raise NotImplementedError("Only mode='cf' is implemented so far.")

    if not per_shape:
        cf_min = cf_mean.min(dim=("x", "y"), skipna=True)
        cf_max = cf_mean.max(dim=("x", "y"), skipna=True)

        # edges(bin_edge)
        edges = cf_min + (cf_max - cf_min) * xr.DataArray(bin_edges, dims="bin_edge")

    if per_shape:
        # Broadcast cf_mean onto the shape dimension and mask it
        # wherever the shape has no availability.
        data = xr.Dataset(
            {"availability": availability, "cf_mean": cf_mean}
        ).broadcast_like(availability)

        data["cf_mean"] = data.cf_mean.where(data.availability > 0)

        cf_min = data.cf_mean.min(dim=("x", "y"), skipna=True)
        cf_max = data.cf_mean.max(dim=("x", "y"), skipna=True)

        # edges(shape_id, bin_edge)
        edges = cf_min + (cf_max - cf_min) * xr.DataArray(bin_edges, dims="bin_edge")

    lower_edges = edges.isel(bin_edge=slice(None, -1))
    upper_edges = edges.isel(bin_edge=slice(1, None))

    # Rename bin_edge -> bin so xarray broadcasts the bin dimension.
    lower_edges = lower_edges.rename(bin_edge="bin")
    upper_edges = upper_edges.rename(bin_edge="bin")

    class_masks = (cf_mean >= lower_edges) & (cf_mean < upper_edges)

    class_masks = class_masks.assign_coords(bin=np.arange(len(bin_edges) - 1))

    if per_shape:
        # select only the grid cells that have availability in each shape
        class_masks = class_masks.where(availability > 0, other=False)
        return class_masks.transpose("bin", "shape_id", "y", "x")

    return class_masks.transpose("bin", "y", "x")
