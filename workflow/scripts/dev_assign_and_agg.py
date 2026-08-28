#%%
from IPython.core.getipython import get_ipython

get_ipython().run_line_magic("load_ext", "autoreload")
get_ipython().run_line_magic("autoreload", "2")

import atlite
import geopandas as gpd
import rioxarray as rxr
from pathlib import Path
from _utils import read_yaml
import matplotlib.pyplot as plt

from _processing import assign_to_shapes_and_aggregate

basepath = Path(__file__).parent.parent.parent

path_cutout=basepath / "resources/user/cutouts_era5_2017.nc"
path_availability=basepath / "resources/user/layouts_raster_europe.tif"
path_shapes=basepath / "resources/user/shapes_NLD_NUTS2_onshore.parquet"
path_shapes=basepath / "resources/user/shapes_Europe_NUTS2_onshore.parquet"
path_tech_specs=basepath / "resources/user/tech_specs_wind_onshore_3MW.yaml"
capacity_per_sq_km =3
bin_edges = None#[0, 0.2, 0.5]

cutout = atlite.Cutout(path_cutout)
availability = rxr.open_rasterio(path_availability).sel(band=1).drop_vars("band")
shapes = gpd.read_parquet(path_shapes)
tech_specs = read_yaml(path_tech_specs)
tech = tech_specs["tech"]
specs = tech_specs["specs"]
specs.pop("per_unit")


#%%
# optional clipping
# availability = availability.sel(x=slice(4.5, 5), y=slice(54, 52))
# availability = availability.sel(x=slice(0, 10), y=slice(54, 45))

#%%
res = assign_to_shapes_and_aggregate(availability, shapes, cutout)

#%%
# confirm shapes are correctly assigned
fig, ax = plt.subplots()
res.sel(shape_id="ESP_nuts2024_ES61").plot(ax=ax)
shapes.loc[shapes.shape_id=="ESP_nuts2024_ES61"].geometry.boundary.plot(ax=ax)

#%%
# compare with reproject match
import rasterio as rio
match = (
    cutout.uniform_layout()
    .rio.write_crs(cutout.crs)
    .rio.write_transform(cutout.transform)
)
availability_reproject = availability.squeeze(drop=True)
availability_reproject = availability_reproject.fillna(0)
availability_reproject = availability_reproject.rio.reproject_match(
    match, resampling=rio.enums.Resampling.sum, nodata=0
)
availability_reproject
#%%

#%%
fig, ax = plt.subplots()
res.sum("shape_id").plot(ax=ax, cmap="viridis")
# shapes.boundary.plot(ax=ax, zorder=4, linewidth=0.3, color="k")
# availability.plot(ax=ax)
# ax.set_xlim(0, 10)
# ax.set_ylim(50,55)


#%%
# confirm that the total availability and the availability per shape is conserved
availability_per_shape = res.sum(["x", "y"]).to_dataframe(name="availability")
# availability_per_shape = res.sum(["cell_number"]).to_dataframe(name="availability")
availability_per_shape
#%%
availability_per_shape
aps = availability_per_shape.merge(
    shapes,
    left_on="shape_id",
    right_on=shapes["shape_id"],
)
aps = gpd.GeoDataFrame(aps)
fig, ax = plt.subplots()
aps.plot(column="availability", ax=ax)
shapes.geometry.boundary.plot(ax=ax, linewidth=0.1)

#%%
from gregor.aggregate import aggregate_raster_to_polygon

a_per_s_direct = aggregate_raster_to_polygon(
    availability,
    shapes.set_index("shape_id")
)
a_per_s_direct = gpd.GeoDataFrame(a_per_s_direct)
#%%

a_per_s_direct
#%%

a_per_s_direct.plot(column="sum")
#%%

compare = gpd.GeoDataFrame(
    availability_per_shape.join(
    a_per_s_direct
    ),
    geometry="geometry"
)

#%%
tol= 0.000001
compare.loc[abs(compare["availability"] - compare["sum"]) > tol]

#%%
# Apply the binning/filtering
# Multiply

#%%
# # change index from in_shape, in_cell to shape_id, x_coarse, y_coarse


# #%%
# import matplotlib.pyplot as plt
# fig, ax = plt.subplots()
# res.sum("in_shape").plot(ax=ax, cmap="Blues")

# #%%
# # new attempt. assign shape as coordinate
# data_n2 = availability.expand_dims("in_shape")
# data_n2 = data_n2.assign_coords(in_shape=belongs_to)

# flat = data_n2.stack(cell=("x", "y"))
# grid_ids = belongs_to_grid.stack(cell=("x", "y")).values
# valid = grid_ids >= 0


# #%%
# import numpy as np
# from scipy.sparse import csr_matrix
# ncell = len(grid_ids)
# ngrid = grid_ids[valid].max() + 1

# # construct a sparse matrix that maps grid cells to raster cells

# rows = grid_ids[valid]
# cols = np.nonzero(valid)[0]
# data = np.ones(valid.sum())
# A = csr_matrix((data, (rows, cols)), shape=(ncell, ngrid))
# doesn't work yet
# Stopped because not sure if there is an efficiency gain
# # %%
# X = flat.values  # (ncell, nshapes)

# result = A @ X
# # %%

# %%
