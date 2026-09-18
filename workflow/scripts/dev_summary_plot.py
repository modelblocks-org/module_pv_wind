#%%
from IPython.core.getipython import get_ipython
get_ipython().run_line_magic("load_ext", "autoreload")
get_ipython().run_line_magic("autoreload", "2")

from _plots import create_summary_plot

import xarray as xr
from pathlib import Path

cutout = "era5_2017"
shape = "Europe_NUTS2_onshore"
layout = "raster_europe"
tech = "wind_onshore_3MW"

basepath = Path(__file__).parent.parent.parent
capacity_factors=f"results/{cutout}/{shape}/{layout}/capacityfactors_{tech}.nc"
capacity_factors_mean=f"results/{cutout}/{shape}/{layout}/capacityfactors_{tech}_mean.nc"
matrix=f"results/{cutout}/{shape}/{layout}/capacityfactors_{tech}_matrix.nc"


create_summary_plot(
    path_cf=basepath / capacity_factors,
    path_cf_mean=basepath / capacity_factors_mean,
    path_matrix=basepath / matrix,
    path_shapes=basepath / f"resources/user/shapes_{shape}.parquet",
    path_output="testssummary.png",
)
# %%
