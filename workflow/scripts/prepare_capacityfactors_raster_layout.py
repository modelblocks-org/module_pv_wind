"""Prepare PV capacityfactors, given a cutout, a layout, shapes to aggregate to and technology specifications."""

import _backend_atlite as _backend_atlite
import geopandas as gpd
import rioxarray as rxr
from _plots import create_plot_map, create_plot_overview
from _schemas import Shapes
from _utils import read_yaml


def prepare_capacityfactors_raster_layout(
    path_cutout, path_shapes, path_tech_specs, path_layout, path_output
):
    """Prepare capacityfactors aggregated to shapes weighted by a raster layout."""
    # load inputs
    shapes = gpd.read_parquet(path_shapes)
    shapes = Shapes.validate(shapes)
    tech_specs = read_yaml(path_tech_specs)
    layout = rxr.open_rasterio(path_layout, masked=True)

    # prepare inputs
    shapes = shapes.set_index("shape_id")
    layout = layout.fillna(0)

    # compute capacityfactors
    capacityfactors = _backend_atlite.cf_aggregated_from_raster_layout(
        path_cutout=path_cutout, layout=layout, shapes=shapes, tech_specs=tech_specs
    )

    # save output
    capacityfactors.to_netcdf(path_output)


if __name__ == "__main__":
    prepare_capacityfactors_raster_layout(
        path_cutout=snakemake.input.cutout,
        path_shapes=snakemake.input.shapes,
        path_tech_specs=snakemake.input.tech_specs,
        path_layout=snakemake.input.layout,
        path_output=snakemake.output.data,
    )
    create_plot_map(
        path_capacityfactors=snakemake.output.data,
        path_shapes=snakemake.input.shapes,
        path_map=snakemake.output.plot_map,
    )
    create_plot_overview(
        path_capacityfactors=snakemake.output.data,
        path_shapes=snakemake.input.shapes,
        path_plot=snakemake.output.plot_overview,
    )
