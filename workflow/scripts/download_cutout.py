"""Download a cutout using atlite."""

import logging

import atlite

logger = logging.getLogger(__name__)


def download_cutout(cutout_path, cutout_params, cutout_features):
    """Downloads a cutout based on the provided parameters."""
    cutout_params["x"] = slice(*cutout_params["x"])
    cutout_params["y"] = slice(*cutout_params["y"])
    cutout_params["time"] = slice(*cutout_params["time"])

    monthly_requests = cutout_params.pop("monthly_requests", False)

    logger.info(f"Preparing cutout with cutout_params: {cutout_params}")
    logger.info(f"Preparing cutout with features: {cutout_features}")

    cutout = atlite.Cutout(cutout_path, **cutout_params)
    cutout.prepare(features=cutout_features, monthly_requests=monthly_requests)


if __name__ == "__main__":
    logger.info(f"Using atlite version: {atlite.__version__}")

    download_cutout(
        cutout_path=snakemake.output[0],
        cutout_params=snakemake.config["cutout_params"],
        cutout_features=snakemake.params["features"],
    )
