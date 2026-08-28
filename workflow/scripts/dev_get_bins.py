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

from _processing import get_bins

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
# %%

get_bins(
    cutout=cutout,
    shapes=shapes,
    tech=tech,
    specs=specs,
    bin_edges=bin_edges,
    per_shape=True,
)

# %%
# We have availability(shape_id, x_coarse, y_coarse)
# We calculate mean_cf(x_coarse, y_coarse)
# We set threshold or bin_edges to get bin_number(x_coarse, y_coarse)
# the final goal is power_potential(shape, bin, x_grid, y_grid)
# The missing piece is data that says: bin(shape, x_grid, y_grid)
