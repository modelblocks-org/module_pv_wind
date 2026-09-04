"""Rules to used to download automatic resource files."""

if config["download_cutout"]:

    rule download_cutout:
        output:
            "<cutout>",
        conda:
            "../envs/atlite.yaml"
        params:
            features=internal["cutout_features"],
        script:
            "../scripts/download_cutout.py"


path_cutout = ancient("<cutout>")
