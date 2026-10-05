rule dummy_add_text:
    input:
        user_file="resources/user/user_message.md",
        readme="resources/automatic/dummy_readme.md",
    output:
        combined="results/combined_text.md",
    log:
        "logs/dummy_add_text.log",
    conda:
        "../envs/shell.yaml"
    params:
        config_text=config["dummy_text"],
    message:
        "Dummy rule combining user inputs and automatic downloads."
    script:
        "../scripts/dummy_script.py"
