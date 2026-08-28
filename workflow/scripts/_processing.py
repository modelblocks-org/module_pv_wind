import time

import geopandas as gpd
import numpy as np
import xarray as xr
from atlite.gis import ExclusionContainer
from gregor.disaggregate import get_belongs_to_matrix
from rasterio.features import rasterize


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


def assign_to_shapes_and_aggregate(availability, shapes, cutout):
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


def assign_to_shapes_and_aggregate3(availability, shapes, cutout):
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


def get_bins_2(cutout, tech, specs, bin_edges=None):
    """Bins the cutout grid according to annual capacity factors.

    Parameters:
    -----------
    cutout: atlite.Cutout
    tech: str
        technology name
    specs: dict
        Technology specifications
    bin_edges: list[float] (optional)
        Edges of the bins (between 0 and 1). If None, a single bin (0, 1) is used.

    Returns:
    --------
    masks: xarray.DataArray
        Boolean masks for each bin
    """
    time_start = time.time()

    # define the  bins
    if bin_edges is None:
        bin_edges = [(0.0, 1.0)]
    else:
        bin_edges = sorted(set(bin_edges) | {0.0, 1.0})

        if not all(0.0 <= edge <= 1.0 for edge in bin_edges):
            raise ValueError("bin_edges must be between 0 and 1.")

    n_bins = len(bin_edges) - 1

    if n_bins == 1:
        # create a mask without computing cf.
        return xr.DataArray(
            np.ones((1, cutout.shape[1], cutout.shape[0]), dtype=bool),
            dims=("bin", "y", "x"),
            coords={"bin": [0]},
        )

    # compute mean capacity factor,
    # as a measure of the resource quality.
    cf_mean = getattr(cutout, tech)(aggregate_time="mean", **specs)
    print(f"Computed mean capacity factor in {time.time() - time_start:.2f} seconds.")

    # map relative bin edges onto the CF range.
    epsilon = 1e-3
    cf_min = cf_mean.min(dim=("x", "y")) - epsilon
    cf_max = cf_mean.max(dim=("x", "y")) + epsilon

    edges = cf_min + (cf_max - cf_min) * xr.DataArray(bin_edges, dims="bin_edge")

    lower = edges.isel(bin_edge=slice(None, -1))
    upper = edges.isel(bin_edge=slice(1, None))

    # Rename the edge dimension so broadcasting produces one dimension
    # for the bins.
    lower = lower.rename(bin_edge="bin")
    upper = upper.rename(bin_edge="bin")

    return ((cf_mean >= lower) & (cf_mean < upper)), cf_mean


def get_bins(cutout, shapes, tech, specs, bin_edges=None, per_shape=False):
    """Get bins.

    Parameters
    ----------
    cutout : atlite.Cutout
        Cutout of meteorological data.
    shapes : gpd.GeoDataFrame
        Shapes to aggregate to.
    tech : str
        Technology, for example "wind" or "pv".
    specs : dict
        Keyword arguments passed to atlite conversion method.
    capacity_per_sq_km : float
        Capacity density of the technology in units of power/area, e.g. MW/km².
    bin_edges : list[float] | None
        Quantile boundaries counted from the top. If None, all resources
        will be aggregated to one bin. Passing a list of quantiles will create bins.
        To include the least productive resources, include 0.0 in the list of quantiles.
    per_shape: bool | False
        If True, resources will be binned per shape, otherwise for the entire cutout.
    """
    # define bins
    if bin_edges is None:
        bins = [(0.0, 1.0)]
    else:
        assert len(bin_edges) == len(set(bin_edges)), (
            "bin_edges should not contain duplicates"
        )
        assert all(0.0 <= b <= 1.0 for b in bin_edges), (
            "bin_edges should be between 0 and 1"
        )
        bin_edges += [1.0]
        bin_edges = sorted(list(set(bin_edges)))
        bins = list(zip(bin_edges[:-1], bin_edges[1:]))

    n_bins = len(bins)

    # get the conversion method
    convert = getattr(cutout, tech)

    I = cutout.availabilitymatrix(shapes, ExclusionContainer())
    print(np.unique(I))
    # I = np.ceil(I)

    if n_bins > 1:
        # compute a raster describing temporal mean capacity factor,
        # as a measure of the resource quality.
        cf_mean = convert(aggregate_time="mean", **specs)

    # get the indicator matrix
    # indicator is 1 if the grid cell belongs to the shape and bin, and 0 otherwise.
    # cells that are partially overlapping are counted in
    # indicator(shape, bin, x, y)
    # TODO: wrap into get_indicator(cutout, shapes, criterion, bins, per_shape)
    if n_bins > 1:
        cf_by_bus = cf_mean * I.where(I > 0)
    else:
        cf_by_bus = I.where(I > 0)

    epsilon = 1e-3
    cf_min, cf_max = (
        cf_by_bus.min(dim=["x", "y"]) - epsilon,
        cf_by_bus.max(dim=["x", "y"]) + epsilon,
    )
    normed_bins = xr.DataArray(np.linspace(0, 1, n_bins + 1), dims=["bin"])
    bins = cf_min + (cf_max - cf_min) * normed_bins

    cf_by_bus_bin = cf_by_bus.expand_dims(bin=range(n_bins))
    lower_edges = bins[:, :-1]
    upper_edges = bins[:, 1:]
    class_masks = (cf_by_bus_bin >= lower_edges) & (cf_by_bus_bin < upper_edges)

    # matrix (area) is a weighted indicator matrix
    # it maps the cutout grid to shapes, and optionally also bins, ifavailab multiple bins are specified.
    # It is weighted by the availability, therefore it is in units of area.
    # we apply the availability here, so that we can later easily compute the power potential.
    # matrix = availability * indicator(shape, bin, x, y)

    return class_masks
