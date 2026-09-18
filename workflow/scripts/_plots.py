from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import xarray as xr
from _schemas import Shapes
from matplotlib.colors import LinearSegmentedColormap
import numpy as np

cmap_wind = LinearSegmentedColormap.from_list("cmap_wind", ["white", "blue"])
cmap_pv = LinearSegmentedColormap.from_list("cmap_pv", ["white", "orange"])

def plot_raster(data, ax, cax, **kwargs):
    # Coordinate-aware plotting also handles descending latitude arrays.
    data.transpose("y", "x").plot.pcolormesh(
        ax=ax, x="x", y="y", cbar_ax=cax,
        cbar_kwargs={"label": ""}, **kwargs,
    )

def create_summary_plot(
    path_cf: str | Path,
    path_cf_mean: str | Path,
    path_matrix: str | Path,
    path_shapes: str | Path,
    path_output: str | Path,
):
    """Plot capacity factors on aligned geographic axes and save the figure."""
    with (
        xr.open_dataarray(path_cf) as cf,
        xr.open_dataarray(path_cf_mean) as cf_mean,
        xr.open_dataarray(path_matrix) as matrix,
    ):
        kwargs_boundary = dict(color="k", linewidth=0.5, alpha=0.5)

        shapes = Shapes.validate(gpd.read_parquet(path_shapes))
        shapes = shapes.to_crs("EPSG:4326")

        fig = plt.figure(figsize=(10, 8), layout="constrained")
        gs = fig.add_gridspec(3, 4, width_ratios=[1, 0.04, 1, 0.04])
        ax_layout = fig.add_subplot(gs[0, 0])
        ax_bins = fig.add_subplot(gs[0, 2])
        ax_cf_mean = fig.add_subplot(gs[1, 0])
        ax_cf = fig.add_subplot(gs[1, 2])
        ax_bar = fig.add_subplot(gs[2, :3])
        ax_layout = fig.add_subplot(gs[0, 1])
        ax_cbar_layout = fig.add_subplot(gs[0, 1])
        ax_cbar_bins = fig.add_subplot(gs[0, 3])
        ax_cbar_cf_mean = fig.add_subplot(gs[1, 1])
        ax_cbar_cf = fig.add_subplot(gs[1, 3])

        # plot layout
        layout = matrix.sum(dim=[d for d in matrix.dims if d not in ("x", "y")])
        plot_raster(layout.where(layout > 0), ax_layout, ax_cbar_layout, cmap="Greys")

        # plot bins
        if "bin" in matrix.dims:
            bin_capacity = matrix.sum(dim="shape_id")
            bins = bin_capacity.argmax(dim="bin").where(layout > 0)
            plot_raster(
                bins, ax_bins, ax_cbar_bins, cmap="tab20",
                levels=np.arange(matrix.sizes["bin"] + 1) - 0.5,
            )
            ax_cbar_bins.set_yticks(np.arange(matrix.sizes["bin"]))
            ax_cbar_bins.set_yticklabels([str(value) for value in matrix.bin.values])
        else:
            ax_bins.text(
                0.5, 0.5, "No capacity factor bins", ha="center", va="center",
                transform=ax_bins.transAxes,
            )
            ax_cbar_bins.set_axis_off()

        plot_raster(cf_mean, ax_cf_mean, ax_cbar_cf_mean, cmap="Reds", vmin=0, vmax=1)

        # plot cf
        annual_cf = cf.mean(dim="time")
        if "bin" in annual_cf.dims:
            weights = matrix.sum(dim=("x", "y")).sel(
                shape_id=annual_cf.shape_id, bin=annual_cf.bin,
            )
            weights = weights.where(annual_cf.notnull(), 0)
            annual_cf = (annual_cf.fillna(0) * weights).sum("bin") / (
                weights.sum("bin").where(lambda total: total > 0)
            )
        cf_geo = shapes.merge(
            annual_cf.to_dataframe(name="mean_capacityfactor").reset_index(),
            on="shape_id", how="left",
        )
        cf_geo.plot(
            ax=ax_cf, cax=ax_cbar_cf, column="mean_capacityfactor", legend=True,
            cmap="Reds", vmin=0, vmax=1, missing_kwds={"color": "lightgray"},
        )

        # Use cell edges from the raster, rather than polygon bounds or pixel indices.
        def coordinate_limits(coord):
            values = np.sort(coord.values)
            lower_step = values[1] - values[0] if len(values) > 1 else 0.25
            upper_step = values[-1] - values[-2] if len(values) > 1 else 0.25
            return values[0] - lower_step / 2, values[-1] + upper_step / 2

        xlim = coordinate_limits(cf_mean.x)
        ylim = coordinate_limits(cf_mean.y)
        aspect = 1 / np.cos(np.deg2rad(np.mean(ylim)))
        for ax, title in zip(
            [ax_layout, ax_bins, ax_cf_mean, ax_cf],
            ["Layout", "Bins", "Mean Capacity Factors", "Weighted Mean Capacity Factors"],
        ):
            shapes.boundary.plot(ax=ax, **kwargs_boundary)
            ax.set_xlim(xlim, auto=True)
            ax.set_ylim(ylim, auto=True)
            # Give every map the same box proportions and geographic scale.
            ax.set_box_aspect(0.5)
            ax.set_aspect(aspect, adjustable="datalim")
            _blank_axis(ax)
            ax.set_title(title)

        # plot overview
        overview = cf_geo.dropna(subset=["mean_capacityfactor"])
        plot_overview(cf=overview, column="mean_capacityfactor", ax=ax_bar)
        ax_bar.set_ylabel("Mean CF")
        ax_bar.set_xlabel("Shapes")
        ax_bar.set_title("Annual Capacity Factors")

        # Match the spanning overview to the actual map edges after aspect sizing.
        fig.canvas.draw()
        fig.set_layout_engine("none")
        bar_position = ax_bar.get_position()
        left = ax_layout.get_position().x0
        right = ax_bins.get_position().x1
        ax_bar.set_position([left, bar_position.y0, right - left, bar_position.height])

        path_output = Path(path_output)
        path_output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path_output)
        return fig



def create_map_capacityfactors(path_capacityfactors, path_shapes, path_output):
    """Creates a map of the mean capacityfactors."""
    cf = xr.open_dataarray(path_capacityfactors)
    shapes = gpd.read_parquet(path_shapes)
    shapes = Shapes.validate(shapes)
    shapes = shapes.set_index("shape_id")

    gdf_mean_cf = shapes.join(
        cf.mean(dim="time").to_dataframe(name="mean_capacityfactor")
    )

    fig, ax = plt.subplots(tight_layout=True)
    map_capacity_factors(gdf_mean_cf=gdf_mean_cf, column="mean_capacityfactor", ax=ax)
    ax.set_title("Mean capacity factor")

    fig.savefig(path_output)



def plot_overview(cf, column, ax=None, sort=True, color="k"):
    """Plots the summary statistics of the capacity factors."""
    COLS = ["shape_id", "country_id", column]
    assert all([col in cf.columns for col in COLS])

    if ax is None:
        _, ax = plt.subplots()

    if sort:
        _cf = cf \
            .sort_values(["country_id", column], ascending=[True, False]) \
            .reset_index(drop=True)
    
    _cf.index.name = "index"
 
    ax.scatter(
        x=_cf.index,
        y=_cf[column],
        marker=".",
        linestyle="",
        linewidth=1,
        color=color,
        alpha=0.7,
        label="Mean CF"
    )

    # grid in 0.05 steps
    vmin = 0
    vmax = _cf[column].max()
    ax.set_yticks(np.arange(vmin, vmax + 0.05, 0.05))
    ax.grid(which="both", axis="y", alpha=0.3)

    # plot a horizontal line for the country average
    country_avg = _cf.groupby("country_id", as_index=False)[column].mean()
    country_avg = pd.merge(
        _cf[["shape_id", "country_id"]],
        country_avg,
    )
    ax.step(
        x=country_avg.index,
        y=country_avg[column],
        where="post",
        color=color,
        alpha=0.2,
        label="Country average"
    )

    # set a major xtick where a new country starts, and label it with the country code
    major = _cf.reset_index().groupby("country_id", as_index=False).first()
    ax.set_xticks(major["index"])

    # set minor xticks and labels at the midpoinst between the major ticks
    ticks = ax.get_xticks()
    midpoints = (ticks[:-1] + ticks[1:]) / 2
    midpoints = midpoints.tolist() + [ticks[-1]]  # add a final midpoint

    ax.set_xticks(midpoints, minor=True)
    ax.set_xticklabels(major["country_id"], rotation=90, fontsize=8, minor=True)
    
    ax.tick_params(axis='x', which='minor', length=0)  # hide minor tick marks
    ax.tick_params(axis='x', which='major', labelbottom=False)  # hide major tick labels
    plt.xticks(fontsize=8)

    # draw vertical lines for wind and pv at the major xticks
    ax.vlines(major["index"], ymin=0, ymax=major[column], color=color, linestyle="-", alpha=0.5)


def _blank_axis(ax):
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel("")
    ax.set_ylabel("")
