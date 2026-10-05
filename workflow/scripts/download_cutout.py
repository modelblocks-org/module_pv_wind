import atlite
import pandas as pd

if __name__ == "__main__":
    cutout_params = snakemake.config["build_cutout"]["cutout_params"]

    snapshots = pd.date_range(freq="h", **snakemake.config["snapshots"])
    time = [snapshots[0], snapshots[-1]]
    cutout_params["time"] = slice(*cutout_params.get("time", time))

    cutout_params["x"] = slice(*cutout_params["x"])
    cutout_params["y"] = slice(*cutout_params["y"])

    features = cutout_params.pop("features", None)
    cutout = atlite.Cutout(snakemake.output[0], **cutout_params)
    cutout.prepare(features=features)
