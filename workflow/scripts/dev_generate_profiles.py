#%%
from IPython.core.getipython import get_ipython

get_ipython().run_line_magic("load_ext", "autoreload")
get_ipython().run_line_magic("autoreload", "2")

import atlite
import numpy as np
import pandas as pd
import geopandas as gpd
import xarray as xr
import rioxarray as rxr
from pathlib import Path
from _utils import read_yaml
from gregor.disaggregate import get_belongs_to_matrix
from atlite.gis import ExclusionContainer


def build_renewables(
    cutout,
    availability,
    shapes,
    tech,
    specs,
    capacity_per_sq_km,
    bin_edges=None,
    per_shape=False,
):
    """
    Build renewable profiles and potentials.

    Parameters
    ----------
    cutout : atlite.Cutout
        Cutout of meteorological data.
    availability : xr.DataArray (y, x)
        Eligible area in units of area, e.g. km².
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
        assert len(bin_edges) == len(set(bin_edges)), "bin_edges should not contain duplicates"
        assert all(0.0 <= b <= 1.0 for b in bin_edges), "bin_edges should be between 0 and 1"
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
        cf_mean = convert(
            aggregate_time="mean",
            **specs,
        )

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

    matrix = availability * cutout.indicatormatrix(shapes)
    # layout is the total area per grid cell, which is the availability multiplied by the capacity density.
    # or just 1? Do we need it? Availability is already in km2, so we can directly compute the power potential by multiplying with the capacity density.
    # layout = area * capacity_per_sq_km

    profiles = convert(
        matrix=matrix,
        per_unit=True,
        **specs,
    )
    
    power_potential = matrix * capacity_per_sq_km

    profiles, p_nom_max, indicator = None, None, None
    return profiles, p_nom_max, indicator

def get_indicator(cutout, shapes, bins, per_shape):
    if len(bins) == 1:
        # if there is only one bin, we can skip the binning step and directly compute the indicator matrix.
        return cutout.indicatormatrix(shapes)

    elif per_shape:
        # if there are multiple bins and we want to bin per shape, we need to compute the indicator matrix for each shape separately.
        indicators = []
        for _, shape in shapes.iterrows():
            indicator_shape = cutout.indicatormatrix(shape.geometry)
            indicators.append(indicator_shape)
        return np.array(indicators)

    else:
        return


basepath = Path(__file__).parent.parent.parent

path_cutout=basepath / "resources/user/cutouts_era5_2017.nc"
path_availability=basepath / "resources/user/layouts_raster_europe.tif"
path_shapes=basepath / "resources/user/shapes_NLD_NUTS2_onshore.parquet"
path_tech_specs=basepath / "resources/user/tech_specs_wind_onshore_3MW.yaml"
capacity_per_sq_km =3
bin_edges = None#[0, 0.2, 0.5]

cutout = atlite.Cutout(path_cutout)
availability = rxr.open_rasterio(path_availability).sel(band=1).drop("band")
shapes = gpd.read_parquet(path_shapes)
tech_specs = read_yaml(path_tech_specs)
tech = tech_specs["tech"]
specs = tech_specs["specs"]
specs.pop("per_unit")


# res = build_renewables(
#     cutout=cutout,
#     availability=availability,
#     shapes=shapes,
#     tech=tech,
#     specs=specs,
#     capacity_per_sq_km=capacity_per_sq_km,
#     bin_edges=bin_edges,
# )


#%%
# matrix is a matrix that describes the power potential for each shape, optionally resource bin, and grid cell,.
# we need to map the availability to the cutout and the shapes.
# option 1 downsample availability. Problem: Too coarse.
# option 2: First map availability to shape, then downsample to cutout.


from rasterio.features import rasterize


def get_belongs_to_matrix(
    raster: xr.DataArray, polygons: gpd.GeoSeries, nodata: int = -1
) -> xr.DataArray:
    r"""
    Get a matrix which indicates which polygon each raster point belongs to.

    Parameters
    ----------
    raster : xr.DataArray
        Raster array to get the matrix for.
    polygons : gpd.GeoSeries
        Polygons to compute the matrix for.
    nodata : int
        Value to use as NaN, i.e. for pixels that do not belong to any polygon.

    Returns
    -------
    xr.DataArray
        Matrix which indicates which polygon each raster point belongs to.
    """
    assert len(raster.dims) == 2, "Raster data should have 2 dimensions."

    shapes = [(geom, i) for i, geom in enumerate(polygons)]
    arr = rasterize(
        shapes,
        out_shape=raster.shape,
        transform=raster.rio.transform(),
        fill=nodata,  # fills invalid cases
        dtype="int32",
    )

    return xr.DataArray(arr, coords=raster.coords, dims=raster.dims)


shapes_reprojected = shapes.to_crs(availability.rio.crs)

# belongs_to(x, y)
# TODO: fix dangerous reliance on the order in get_belongs_to_matrix.
# TODO: Document that partial membership is not supported, which is ok if grid is fine compared to polygons
belongs_to = get_belongs_to_matrix(availability, shapes_reprojected.set_index("shape_id").geometry)

# sparse indicator_matrix(shape, x_avail, y_avail) 
# indicator_matrix = belongs_to.expand_dims(shape=range(len(shapes_reprojected)))
# indicator_matrix = (indicator_matrix == list(range(len(shapes_reprojected))))
import sparse

def get_availability_matrix(belongs_to: xr.DataArray, availability: xr.DataArray) -> sparse.COO:
    y, x = np.nonzero(belongs_to.values >= 0)

    country = belongs_to.values[y, x],  # country

    availability_matrix = sparse.COO(
        coords=np.vstack([country, y, x]),
        data=availability.values[x, y],
        shape=(n, *belongs_to.values.shape),
    )
    return availability_matrix

availability_matrix = get_availability_matrix(belongs_to, availability)
availability_matrix

#%%
# next attempt, not using the indicator matrix.
# instead, we create belongs_to_shape, belongs_to_grid.
# with this, we create availabilty(shape, x_grid, y_grid)

belongs_to_shapes = get_belongs_to_matrix(availability, shapes_reprojected.set_index("shape_id").geometry)

grid_reprojected = cutout.grid.to_crs(availability.rio.crs)
belongs_to_grid = get_belongs_to_matrix(availability, grid_reprojected.geometry)
belongs_to_grid

# Can I use the streaming and sparsity while still retaining understandability? Ideally, I want to use
# area with belongs_to_shape to create area(shape, x_f, y_f), then aggregate to x_grid, y_grid using belongs_to_grid, then mapping to bins by applying bin(x_grid, y_grid). Can I write everything as operations between these objects but still be efficient on memory?

def get_shape_coarse_matrix(
    value: xr.DataArray,
    shape_map: xr.DataArray,
    coarse_map: xr.DataArray,
) -> sparse.COO:
    """
    Returns sparse tensor: (shape, coarse)
    """
    v = value.values

    y, x = np.nonzero(v >= 0)
    data = v[y, x]

    shape = shape_map.values[y, x]
    coarse = coarse_map.values[y, x]

    coords = np.vstack([shape, coarse])

    out_shape = (
        shape_map.values.max() + 1,
        coarse_map.values.max() + 1,
    )

    return sparse.COO(
        coords=coords,
        data=data,
        shape=out_shape,
    )

get_shape_coarse_matrix(
    availability,
    belongs_to_shapes,
    belongs_to_grid,
)

#%%
fig, ax = plt.subplots()
availability.rio.reproject("EPSG:4326").plot(ax=ax)
cutout.grid.boundary.plot(ax=ax)
ax.set_xlim(-3, 5)
ax.set_ylim(45, 50)

# potential = sparse.COO(
#     coords,
#     values,
#     shape=indicator.shape,
# )
# potential


# map x_avail, y_avail to x_cutout, y_cutout. By resampling


#%%
# final goal: potential(shape, bin, x_cutout, y_cutout)
# for now: potential(shape, x_cutout, y_cutout)
# Because of the limited resolution of the cutout, 
# this one doesn't need to be sparse, at least for now






# %%
# def main(
#     path_cutout,
#     path_availability,
#     path_shapes,
#     path_tech_specs,
#     capacity_per_sq_km,
#     bin_edges=None,
# ):
#     cutout = atlite.Cutout(path_cutout)
#     availability = xr.open_dataarray(path_availability)
#     shapes = gpd.read_parquet(path_shapes)
#     tech_specs = read_yaml(path_tech_specs)
#     tech = tech_specs["tech"]
#     specs = tech_specs["specs"]
#     specs.pop("per_unit")

#     profiles, potentials, indicator = build_renewables(
#         cutout=cutout,
#         availability=availability,
#         shapes=shapes,
#         tech=tech,
#         specs=specs,
#         capacity_per_sq_km=capacity_per_sq_km,
#         bin_edges=bin_edges,
#     )

#     # profiles.to_netcdf("profiles.nc")
#     # potentials.to_netcdf("potentials.nc")
#     # indicator.to_netcdf("indicator.nc")
#     return get_indicator(cutout, shapes, bins=[(0,1)], per_shape=False)



# # if __name__ == "__main__":

# basepath = Path(__file__).parent.parent.parent

# main(
#     path_cutout=basepath / "resources/user/cutouts_era5_2017.nc",
#     path_availability=basepath / "resources/user/layouts_raster_europe.tif",
#     path_shapes=basepath / "resources/user/shapes_NLD_NUTS2_onshore.parquet",
#     path_tech_specs=basepath / "resources/user/tech_specs_wind_onshore_3MW.yaml",
#     capacity_per_sq_km=1000,
#     bin_edges=[0.2, 0.5],
# )
# fig, ax = plt.subplots()
# res.sel(bin=0).sum(dim="dim_0").plot(cmap="Reds", ax=ax)
# shapes.plot(ax=ax, facecolor="none", edgecolor="black")
# ax.set_ylim(51., 54)
# ax.set_xlim(3., 8)