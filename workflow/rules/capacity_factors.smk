if config["layout"] == "raster":

    rule prepare_capacityfactors_raster_layout:
        input:
            cutout=path_cutout,
            tech_specs="<tech_specs>",
            layout="<layout_raster>",
            shapes="<shapes>",
        output:
            cf="<capacity_factors>",
            cf_mean="<capacity_factors_mean>",
            matrix="<matrix>",
            plot="<plot>",
        conda:
            "../envs/atlite.yaml"
        script:
            "../scripts/prepare_capacityfactors_raster_layout.py"

elif config["layout"] == "point":

    rule prepare_capacityfactors_point_layout:
        input:
            cutout=path_cutout,
            tech_specs="<tech_specs>",
            layout="<layout_point>",
            shapes="<shapes>",
        output:
            data="<capacity_factors>",
            plot="<plot>",
        conda:
            "../envs/atlite.yaml"
        script:
            "../scripts/prepare_capacityfactors_point_layout.py"
