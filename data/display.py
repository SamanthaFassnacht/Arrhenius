from os import path
from typing import List, Tuple

from data.resources import OUTPUT_REL_PATH
from data.writer import NetCDFWriter
from data.grid import LatLongGrid, GridDimensions,\
    extract_multidimensional_grid_variable

from core.output_config import global_output_center, ReportDatatype, Debug,\
    DATASET_VARS, IMAGES, IMAGES_PATH, DATASET_VARS_PATH

from pathlib import Path
from mpl_toolkits.basemap import Basemap

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import numpy as np


OUTPUT_FULL_PATH = path.join(Path('.').absolute(), OUTPUT_REL_PATH)

# Keys in the dictionary below.
VAR_TYPE = "Type"
VAR_RANGE = "Range"

VAR_ATTRS = "Attrs"
VAR_UNITS = "Units"
VAR_DESCRIPTION = "Desc"

# Data describing each variable in the dataset.
VARIABLE_METADATA = {
    ReportDatatype.REPORT_TEMP.value: {
        VAR_TYPE: np.float32,
        VAR_RANGE: (-60, 60),
        VAR_ATTRS: {
            VAR_UNITS: "Degrees Celsius",
            VAR_DESCRIPTION: "Final temperature of the grid cell that is"
                             "centered at the associated latitude and"
                             "longitude coordinates"
        }
    },
    ReportDatatype.REPORT_TEMP_CHANGE.value: {
        VAR_TYPE: np.float32,
        VAR_RANGE: (-8, 8),
        VAR_ATTRS: {
            VAR_UNITS: "Degrees Celsius",
            VAR_DESCRIPTION: "Temperature change observed due to CO2 change"
                             "for the grid cell that is centered at the"
                             "associated latitude and longitude coordinates"
        }
    },
    ReportDatatype.REPORT_HUMIDITY.value: {
        VAR_TYPE: np.float32,
        VAR_RANGE: (0, 100),
        VAR_ATTRS: {
            VAR_UNITS: "Percent Saturation",
            VAR_DESCRIPTION: "Final relative humidity of the grid cell"
                             "centered at the associated latitude and"
                             "longitude coordinates"
        }
    },
    ReportDatatype.REPORT_ALBEDO.value: {
        VAR_TYPE: np.float32,
        VAR_RANGE: (0.5, 1),
        VAR_ATTRS: {
            VAR_UNITS: "Decimal Absorption",
            VAR_DESCRIPTION: "Percent of incoming solar energy absorbed"
                             "by the Earth's surface within the grid cell"
                             "centered at the associated latitude and"
                             "longitude coordinates"
        }
    },
}


class ModelImageRenderer:
    """
    A converter between gridded climate data and image visualizations of the
    data. Displays data in the form of nested lists or arrays as an overlay
    on a world map projection.
    """
    def __init__(self: 'ModelImageRenderer',
                 data: np.ndarray) -> None:
        """
        Instantiate a new ModelImageReader.

        Data to display is provided through the data parameter. This parameter
        may either by an array, or an array-like structure such as a nested
        list. the There must be three dimensions to the data: time first,
        followed by latitude and longitude.

        :param data:
            An array-like structure of numeric values, representing temperature
            over a globe
        """
        self._data = data
        self._grid = GridDimensions((len(data), len(data[0])), "count")

        # Some parameters for the visualization are also left as attributes.
        self._continent_linewidth = 0.5
        self._lat_long_linewidth = 0.1

    def save_image(self: 'ModelImageRenderer',
                   out_path: str,
                   min_max_grades: Tuple[int, int] = (-60, 60)) -> None:
        """
        Produces a .PNG formatted image file containing the gridded data
        overlaid on a map projection.

        The map is displayed in equirectangular projection, labelled with
        lines of latitude and longitude at the intersection between
        neighboring grid cells. The grid cells are filled in with a colour
        denoting the magnitude of the temperature at that cell.

        The optional min_max_grades parameter specifies the lower bound and
        the upper bound of the range of values for which different colours
        are assigned. Any grid cell with a temperature value below the first
        element of min_max_grades will be assigned the same colour. The same
        applies to any cell with a temperature greater than min_max_grades[1].
        The default boundaries are -60 and 40.

        The image is saved at the specified absolute or relative filepath.

        :param out_path:
            The location where the image file is created
        :param min_max_grades:
            A tuple containing the boundary values for the colorbar shown in
            the image file
        """
        if len(min_max_grades) != 2:
            raise ValueError("Color grade boundaries must be given in a tuple"
                             "of length 2 (is length {})"
                             .format(len(min_max_grades)))
        # Create an empty world map in equirectangular projection.
        map = Basemap(llcrnrlat=-90, llcrnrlon=-180,
                      urcrnrlat=90, urcrnrlon=180)
        map.drawcoastlines(linewidth=self._continent_linewidth)

        # Construct a grid from the horizontal and vertical sizes of the cells.
        grid_by_width = self._grid.dims_by_width()

        lat_val = -90.0
        lats = []
        while lat_val <= 90:
            lats.append(lat_val)
            lat_val += grid_by_width[0]

        lon_val = -180.0
        lons = []
        while lon_val <= 180:
            lons.append(lon_val)
            lon_val += grid_by_width[1]

        map.drawparallels(lats, linewidth=self._lat_long_linewidth)
        map.drawmeridians(lons, linewidth=self._lat_long_linewidth)
        x, y = map(lons, lats)

        # Overlap the gridded data on top of the map, and display a colour
        # legend with the appropriate boundaries.
        img = map.pcolormesh(x, y, self._data, cmap=plt.cm.get_cmap("jet"))
        map.colorbar(img)
        plt.clim(min_max_grades[0], min_max_grades[1])
        # Save the image and clear added components from memory
        plt.savefig(out_path)
        plt.close()


def write_image_type(data: np.ndarray,
                     output_path: str,
                     data_type: str,
                     run_id: str) -> None:
    """
    Write out a category of output, given by the parameter data, to a
    directory with the name given by output_path. One image file will
    be produced for every index in the highest-level dimension in the
    data.

    The third ard fourth parameters specify the name of the variable
    being represented by this set of images, and the name of the model
    run respectively. EAch image's name will begin with run_id followed
    by an underscore followed by data_type. These will be followed by a
    number indicating the order in which the images were written.

    :param data:
        A single-variable grid derived from Arrhenius model output
    :param output_path:
        The directory where image files will be stored
    :param data_type:
        The name of the variable on which the data is based
    :param run_id:
        A unique name for the current model run
    """
    output_center = global_output_center()
    output_center.submit_output(Debug.PRINT_NOTICES,
                                "Preparing to write {} images"
                                .format(data_type))

    img_base_name = "_".join([run_id, data_type])
    file_ext = '.png'

    # Write an image file for each time segment.
    for i in range(len(data)):
        img_name = "_".join([img_base_name, str(i + 1) + file_ext])
        img_path = path.join(output_path, img_name)

        Path(output_path).mkdir(exist_ok=True)

        # Produce and save the image.
        output_center.submit_output(Debug.PRINT_NOTICES,
                                    "\tSaving image file {}...".format(i))
        g = ModelImageRenderer(data[i])
        g.save_image(img_path, (-1, 1))


class ModelOutput:
    """
    A general-purpose center for all forms of output. Responsible for
    organization of program output into folders.

    The output of a program is defined as the temperature data produced by
    a run of the model. This data may be saved in the form of a data file
    (such as a NetCDF file) and/or as image representations, and/or in other
    data formats.

    All of these output types are produced side-by-side, and stored in their
    own directory to keep data separate from different model runs.
    """

    def __init__(self: 'ModelOutput',
                 data: List['LatLongGrid']) -> None:
        """
        Instantiate a new ModelOutput object.

        Model data is provided through the data parameter, through a list of
        grid objects. Each grid in the list represents a segment of time, such
        as a month or a season. All grids must have the same dimensions.

        :param data:
            A list of latitude-longitude grids of data
        """
        # Create output directory if it does not already exist.
        parent_out_dir = Path(OUTPUT_FULL_PATH)
        parent_out_dir.mkdir(exist_ok=True)

        self._data = data
        self._grid = data[0].dimensions()
        self._dataset = NetCDFWriter()

    def write_dataset(self: 'ModelOutput',
                      data: List['LatLongGrid'],
                      dir_path: str,
                      dataset_name: str) -> None:
        """
        Produce a NetCDF dataset, with the name given by dataset_name.nc,
        containing the variables in the data parameter that the output
        controller allows. The dataset will be written to the specified
        path in the file system.

        The dataset contains all the dimensions that are used in the data
        (e.g. time, latitude, longitude) as well as variables including
        final temperature, temperature change, humidity, etc. according
        to which of the ReportDatatype output types are enabled in the
        current output controller.

        :param data:
            Output from an Arrhenius model run
        :param dir_path:
            The directory where the dataset will be written
        :param dataset_name:
            The name of the dataset
        """
        # Write the data out to a NetCDF file in the output directory.
        grid_by_count = self._grid.dims_by_count()
        output_path = path.join(dir_path, dataset_name)

        global_output_center().submit_output(Debug.PRINT_NOTICES,
                                             "Writing NetCDF dataset...")
        self._dataset.global_attribute("description", "Output for an"
                                                      "Arrhenius model run.")\
            .dimension('time', np.int32, len(data), (0, len(data)))\
            .dimension('latitude', np.int32, grid_by_count[0], (-90, 90)) \
            .dimension('longitude', np.int32, grid_by_count[1], (-180, 180)) \

        for output_type in ReportDatatype:
            variable_data =\
                extract_multidimensional_grid_variable(data,
                                                       output_type.value)
            global_output_center().submit_output(output_type, variable_data,
                                                 output_type.value)

        self._dataset.write(output_path)

    def write_dataset_variable(self: 'ModelOutput',
                               data: np.ndarray,
                               data_type: str) -> None:
        """
        Prepare to write data into a variable by the name of data_type
        in this instance's NetCDF dataset file. Apply this variable's
        dimensions and type, along with several attributes.

        :param data:
            A single-variable grid taken from Arrhenius model output
        :param data_type:
            The name of the variable as it will appear in the dataset
        """
        dims_map = [
            [],
            ['latitude'],
            ['latitude', 'longitude'],
            ['time', 'latitude', 'longitude'],
            ['time', 'level', 'latitude', 'longitude']
        ]

        global_output_center().submit_output(Debug.PRINT_NOTICES,
                                             "Writing {} to dataset"
                                             .format(data_type))
        variable_type = VARIABLE_METADATA[data_type][VAR_TYPE]
        self._dataset.variable(data_type, variable_type, dims_map[data.ndim])

        for attr, val in VARIABLE_METADATA[data_type][VAR_ATTRS].items():
            self._dataset.variable_attribute(data_type, attr, val)

        self._dataset.data(data_type, data)

    def write_images(self: 'ModelOutput',
                     data: List['LatLongGrid'],
                     output_path: str,
                     run_id: str = "") -> None:
        """
        Produce a series of maps displaying some of the results of an
        Arrhenius model run according to what variable the output controller
        allows. Images are stored in a directory given by output_path.

        One image will be produced per time segment per variable for which
        output is allowed by the output controller, based on which
        ReportDatatype output types are enabled. The optional argument
        img_base_name specifies a prefix that will be added to each of the
        image files to identify which model run they belong to.

        :param data:
            The output from an Arrhenius model run
        :param output_path:
            The directory where image files will be stored
        :param run_id:
            A prefix that will start off the names of all the image files
        """
        output_controller = global_output_center()

        # Attempt to output images for each variable output type.
        for output_type in ReportDatatype:
            variable_name = output_type.value
            variable = extract_multidimensional_grid_variable(data,
                                                              variable_name)
            img_type_path = path.join(output_path, variable_name)

            output_controller.submit_output(output_type, variable,
                                            img_type_path,
                                            variable_name,
                                            run_id)

    def write_output(self: 'ModelOutput',
                     run_title: str) -> None:
        """
        Produce NetCDF data files and image files from the provided data, and
        a directory with the name dir_name to hold them.

        One image file is created per time segment in the data. In the
        case of Arrhenius' model, this is one per season. Only one NetCDF data
        file is produced, in which all time segments are present.
        """
        # Create a directory for this model output if none exists already.
        out_dir_path = path.join(OUTPUT_FULL_PATH, run_title)
        out_dir = Path(out_dir_path)
        out_dir.mkdir(exist_ok=True)

        output_controller = global_output_center()
        output_controller.submit_collection_output((DATASET_VARS,),
                                                   self._data,
                                                   out_dir_path,
                                                   run_title + ".nc")
        output_controller.submit_collection_output((IMAGES,),
                                                   self._data,
                                                   out_dir_path,
                                                   run_title)


def write_model_output(data: List['LatLongGrid'],
                       output_title: str) -> None:
    """
    Write the results of a model run (data) to disk, in the form of a
    NetCDF dataset and a series of image files arranged into a directory
    with the name given by output_title.

    :param data:
        The output from an Arrhenius model run
    :param output_title:
        A unique name for the output directory
    """
    writer = ModelOutput(data)
    controller = global_output_center()

    # Upload collection handlers for dataset and image file collections.
    controller.register_collection(DATASET_VARS, handler=writer.write_dataset)
    controller.register_collection(IMAGES, handler=writer.write_images)

    # Change several output type handlers within each collection.
    for output_type in ReportDatatype:
        controller.change_handler_if_enabled(output_type,
                                             (DATASET_VARS,),
                                             writer.write_dataset_variable)
        controller.change_handler_if_enabled(output_type,
                                             (IMAGES,),
                                             write_image_type)

    writer.write_output(output_title)
