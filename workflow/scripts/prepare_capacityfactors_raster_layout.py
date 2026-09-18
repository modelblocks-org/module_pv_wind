"""Prepare PV capacityfactors, given a cutout, a layout, shapes to aggregate to and technology specifications."""

import geopandas as gpd
import rioxarray as rxr
from _backend_atlite._aggregate_raster_layout import cf_aggregated_from_raster_layout
from _plots import create_summary_plot
from _schemas import Shapes
from _utils import read_yaml


def prepare_capacityfactors_raster_layout(
    path_cutout, path_shapes, path_tech_specs, path_layout, path_output_cf, path_output_cf_mean, path_output_matrix
):
    """Prepare capacityfactors aggregated to shapes weighted by a raster layout."""
    # load inputs
    shapes = gpd.read_parquet(path_shapes)
    shapes = Shapes.validate(shapes)
    tech_specs = read_yaml(path_tech_specs)
    layout = rxr.open_rasterio(path_layout, masked=True).squeeze()

    # prepare inputs
    layout = layout.fillna(0)

    # compute capacityfactors
    capacityfactors, cf_mean, matrix = cf_aggregated_from_raster_layout(
        path_cutout=path_cutout, layout=layout, shapes=shapes, tech_specs=tech_specs
    )

    # save output
    capacityfactors.to_netcdf(path_output_cf)
    cf_mean.to_netcdf(path_output_cf_mean)
    matrix.unstack().to_netcdf(path_output_matrix)


if __name__ == "__main__":
    prepare_capacityfactors_raster_layout(
        path_cutout=snakemake.input.cutout,
        path_shapes=snakemake.input.shapes,
        path_tech_specs=snakemake.input.tech_specs,
        path_layout=snakemake.input.layout,
        path_output_cf=snakemake.output.cf,
        path_output_cf_mean=snakemake.output.cf_mean,
        path_output_matrix=snakemake.output.matrix,
    )
    create_summary_plot(
        path_cf=snakemake.output.cf,
        path_cf_mean=snakemake.output.cf_mean,
        path_matrix=snakemake.output.matrix,
        path_shapes=snakemake.input.shapes,
        path_output=snakemake.output.plot,
    )
