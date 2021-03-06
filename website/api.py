from flask import request, jsonify, send_from_directory
from website import app

from os import path
from pathlib import Path
import shutil

from core.configuration import from_json_string, RUN_ID
from core.output_config import ReportDatatype, IMAGES_PATH,\
    default_output_config
from core.runner import ModelRun

from data.display import OUTPUT_FULL_PATH
from data.provider import PROVIDERS


var_name_to_output_type = {
    output_type.value: output_type for output_type in ReportDatatype
}

# A dictionary illustrating proper ranges of values for model config options.
example_config = {
    "co2": {
        "from": [1],
        "to": [0.67, 1.0, 1.5, 2.0, 2.5, 3.0]
    },
    "year": "1895",
    "grid": {
        "dims": {
            "lat": "(0, 180]",
            "lon": "(0, 360]"
        },
        "repr": ["count", "width"]
    },
    "num_layers": "[1, ...)",
    "num_iters": "[1, ...)",
    "aggregate_lat": ["before", "after", None],
    "aggregate_level": ["before", "after"],
    "temp_src": [func_name for func_name in PROVIDERS['temperature']],
    "humidity_src": [func_name for func_name in PROVIDERS['humidity']],
    "albedo_src": [func_name for func_name in PROVIDERS['albedo']],
    "absorbance_src": ["table"],
    "CO2_weight": ["closest", "low", "high", "mean"],
    "H2O_weight": ["closest", "low", "high", "mean"],
}


@app.route('/model/help', methods=['GET'])
def config_options():
    """
    Returns a response to an HTTP request for example configuration options.

    If the request is a GET request, the response contains a template for
    a configuration dictionary, most of the keys of which point to strings
    or lists that specify the range of values acceptable for that key.

    :return:
        An HTTP response containing an example configuration dictionary.
    """
    return jsonify(example_config), 200


@app.route('/model/dataset', methods=['POST'])
def scientific_dataset():
    """
    Returns a response to an HTTP request for the NetCDF dataset associated
    with a specified set of model configuration options.

    If the request is a POST request, a configuration dictionary is expected
    in the request body in the form of a JSON string. Assuming the
    configuration options are valid, the dataset object will be returned that
    was produced by a model run using the specified configuration options.

    :return:
        An HTTP response with the requested dataset attached
    """
    # Decode JSON string from request body.
    config = from_json_string(request.data.decode("utf-8"))
    run_id = str(config[RUN_ID])
    response_code = 200

    dataset_name = run_id + ".nc"
    dataset_parent = path.join(OUTPUT_FULL_PATH, run_id)

    if not Path(dataset_parent, dataset_name).is_file():
        # Model run on the provided configuration options has not been run;
        # run it, producing the output directory as well as image files for
        # the requested variable.
        output_center = default_output_config()

        # Use initial and final CO2 levels from request body if present, but
        # replace with 1 and 2 if not specified.
        init_co2 = float(config.get("co2", 1).get("from", 1))
        final_co2 = float(config.get("co2", 2).get("to", 2))

        run = ModelRun(config, output_center)
        run.run_model(init_co2, final_co2)
        response_code = 201

    # Send the zip file attached to the HTTP response.
    return send_from_directory(dataset_parent, dataset_name),\
        response_code


@app.route('/model/<varname>/<time_seg>', methods=['POST'])
def single_model_data(varname: str, time_seg: str):
    """
    Returns a response to an HTTP request for one image file produced by
    a run of the Arrhenius model, that are associated with variable varname.

    If the request is a POST request, a configuration dictionary is expected
    in the request body in the form of a JSON string. Assuming the
    configuration options are valid, an image file will be attached to the
    response that represents a map of the globe, overlaid with the results
    of a model run with the given configuration options.

    More specifically, the image file is the time_seg'th map produced for
    variable varname under the relevant model run.

    :param varname:
        The name of the variable that is overlaid on the map
    :param time_seg:
        A specifier for which month, season, or general time gradation
        the map should represent
    :return:
        An HTTP response with the requested image file attached
    """
    # Decode JSON string from request body.
    config = from_json_string(request.data.decode("utf-8"))
    run_id = str(config[RUN_ID])
    response_code = 200

    if not Path(OUTPUT_FULL_PATH, run_id, varname).exists():
        # Model run on the provided configuration options has not been run;
        # run it, producing the output directory as well as image files for
        # the requested variable.
        output_center = default_output_config()
        output_center.enable_output_type(var_name_to_output_type[varname],
                                         IMAGES_PATH)

        # Use initial and final CO2 levels from request body if present, but
        # replace with 1 and 2 if not specified.
        init_co2 = float(config.get("co2", 1).get("from", 1))
        final_co2 = float(config.get("co2", 2).get("to", 2))

        run = ModelRun(config, output_center)
        run.run_model(init_co2, final_co2)
        response_code = 201

    # Find and return the requested image file from the output directory.
    download_path = path.join(OUTPUT_FULL_PATH, run_id, varname)
    file_name = "_".join([run_id, varname, time_seg + ".png"])
    return send_from_directory(download_path, file_name), response_code


@app.route('/model/<varname>', methods=['POST'])
def multi_model_data(varname: str):
    """
    Returns a response to an HTTP request for all image files produced by
    a run of the Arrhenius model, that are associated with variable varname.

    If the request is a POST request, a configuration dictionary is expected
    in the request body in the form of a JSON string. Assuming the
    configuration options are valid, a zip archive will be attached to the
    response that contains all image maps that are overlaid with variable
    varname.

    :param varname:
        The name of the variable that is overlaid on the map
    :return:
        An HTTP response with requested image files attached, in a zip file
    """
    # Decode JSON string from request body.
    config = from_json_string(request.data.decode("utf-8"))
    run_id = str(config[RUN_ID])
    response_code = 200

    # This series of zip-file-related names makes the purpose of each
    # more recognizable, but is not really necessary.
    archive_name = "_".join([run_id, varname]) + ".zip"
    archive_src = path.join(OUTPUT_FULL_PATH, run_id, varname)
    archive_parent = path.join(OUTPUT_FULL_PATH, run_id)
    archive_path = path.join(archive_parent, archive_name)

    if not Path(OUTPUT_FULL_PATH, run_id, varname).exists():
        # Model run on the provided configuration options has not been run;
        # run it, producing the output directory as well as image files for
        # the requested variable.
        output_center = default_output_config()
        output_center.enable_output_type(var_name_to_output_type[varname],
                                         IMAGES_PATH)

        # Use initial and final CO2 levels from request body if present, but
        # replace with 1 and 2 if not specified.
        init_co2 = float(config.get("co2", 1).get("from", 1))
        final_co2 = float(config.get("co2", 2).get("to", 2))

        run = ModelRun(config, output_center)
        run.run_model(init_co2, final_co2)
        response_code = 201

    if not Path(archive_path).is_file():
        # The zip file has not been made yet: zip the directory for
        # image files in the requested variable.
        shutil.make_archive(archive_path[:-4], 'zip', archive_src)

    # Send the zip file attached to the HTTP response.
    return send_from_directory(archive_parent, archive_name),\
        response_code

