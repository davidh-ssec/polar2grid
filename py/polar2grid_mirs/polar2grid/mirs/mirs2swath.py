#!/usr/bin/env python
# encoding: utf-8
# Copyright (C) 2014 Space Science and Engineering Center (SSEC),
# University of Wisconsin-Madison.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# This file is part of the polar2grid software package. Polar2grid takes
# satellite observation data, remaps it, and writes it to a file format for
#     input into another program.
# Documentation: http://www.ssec.wisc.edu/software/polar2grid/
#
# Written by David Hoese    September 2014
# University of Wisconsin-Madison
# Space Science and Engineering Center
# 1225 West Dayton Street
# Madison, WI  53706
# david.hoese@ssec.wisc.edu
"""Polar2Grid frontend for extracting data and metadata from files processed by the
Microwave Integrated Retrieval System (MIRS).

:author:       David Hoese (davidh)
:contact:      david.hoese@ssec.wisc.edu
:organization: Space Science and Engineering Center (SSEC)
:copyright:    Copyright (c) 2014 University of Wisconsin SSEC. All rights reserved.
:date:         Sept 2014
:license:      GNU GPLv3

"""
__docformat__ = "restructuredtext en"

import os
import sys
import logging
from datetime import datetime, timedelta
import numpy
from netCDF4 import Dataset

from polar2grid.core import roles
from polar2grid.core.fbf import FileAppender
from polar2grid.core.dtype import numpy_to_dtype
from polar2grid.core import meta

LOG = logging.getLogger(__name__)

# File types (only one for now)
FT_IMG = "MIRS_IMG"
# File variables
RR_VAR = "rr"
BT_88_VAR = "bt_88"
FREQ_VAR = "freq"
LAT_VAR = "latitude"
LON_VAR = "longitude"
BT_VARS = [BT_88_VAR]

### PRODUCT DEFINITIONS ###
# FIXME: Move ProductDefiniton to polar2grid.core
class ProductDefinition(object):
    def __init__(self, name, data_kind, dependencies=None, description=None, units=None):
        self.name = name
        self.data_kind = data_kind
        self.dependencies = dependencies or []
        self.description = description or ""
        self.units = units or ""


class MIRSProductDefiniton(ProductDefinition):
    def __init__(self, name, data_kind, file_type, file_key, dependencies=None, description=None, units=None,
                 is_geoproduct=False):
        self.file_type = file_type
        self.file_key = file_key
        self.is_geoproduct = is_geoproduct
        super(MIRSProductDefiniton, self).__init__(name, data_kind,
                                                   dependencies=dependencies, description=description, units=units)


class ProductList(dict):
    def __init__(self, base_class=ProductDefinition):
        self.base_class = base_class
        super(ProductList, self).__init__()

    def add_product(self, *args, **kwargs):
        pd = self.base_class(*args, **kwargs)
        self[pd.name] = pd

PRODUCT_RAIN_RATE = "rain_rate"
PRODUCT_BT_88 = "btemp_88"
PRODUCT_LATITUDE = "latitude"
PRODUCT_LONGITUDE = "longitude"

PRODUCTS = ProductList(base_class=MIRSProductDefiniton)
PRODUCTS.add_product(PRODUCT_RAIN_RATE, "rain_rate", FT_IMG, RR_VAR,
                     description="Rain Rate", units="mm/hr")
PRODUCTS.add_product(PRODUCT_BT_88, "btemp", FT_IMG, BT_88_VAR,
                     description="Channel Brightness Temperature at 88.2GHz", units="K")
PRODUCTS.add_product(PRODUCT_LATITUDE, "latitude", FT_IMG, LAT_VAR,
                     description="Latitude", units="degrees", is_geoproduct=True)
PRODUCTS.add_product(PRODUCT_LONGITUDE, "longitude", FT_IMG, LON_VAR,
                     description="Longitude", units="degrees", is_geoproduct=True)
GEO_PRODUCTS = [PRODUCT_LONGITUDE, PRODUCT_LATITUDE]

### I/O Operations ###


class MIRSFileReader(object):
    """Basic MIRS file reader.

    If there are alternate formats/structures for MIRS files then new classes should be made.
    """
    FILE_TYPE = FT_IMG

    GLOBAL_FILL_ATTR_NAME = "missing_value"
    # Constant -> (var_name, scale_attr_name, fill_attr_name, frequency)
    FILE_STRUCTURE = {
        RR_VAR: ("RR", "scale", None, None),
        BT_88_VAR: ("BT", "scale", None, 88.2),
        FREQ_VAR: ("Freq", None, None, None),
        LAT_VAR: ("Latitude", None, None, None),
        LON_VAR: ("Longitude", None, None, None),
    }

    def __init__(self, filepath):
        self.filename = os.path.basename(filepath)
        self.filepath = os.path.realpath(filepath)
        self.nc_obj = Dataset(self.filepath, "r")
        if not self.handles_file(self.nc_obj):
            LOG.error("Unknown file format for file %s" % (self.filename,))
            raise ValueError("Unknown file format for file %s" % (self.filename,))

        self.satellite = self.nc_obj.satellite_name
        self.instrument = self.nc_obj.instrument_name
        self.begin_time = datetime.strptime(self.nc_obj.time_coverage_start, "%Y-%m-%dT%H:%M:%SZ")
        self.end_time = datetime.strptime(self.nc_obj.time_coverage_end, "%Y-%m-%dT%H:%M:%SZ")
        self.x_res = float(self.nc_obj.geospatial_lon_resolution)
        self.y_res = float(self.nc_obj.geospatial_lat_resolution)

    @classmethod
    def handles_file(cls, fn_or_nc_obj):
        """Validate that the file this object represents is something that we actually know how to read.
        """
        try:
            if isinstance(fn_or_nc_obj, str):
                nc_obj = Dataset(fn_or_nc_obj, "r")
            else:
                nc_obj = fn_or_nc_obj

            assert(nc_obj.project == "Microwave Integrated Retrieval System")
            assert(nc_obj.title == "MIRS IMG")
            assert(nc_obj.data_model == "NETCDF4")
            return True
        except AssertionError:
            LOG.debug("File Validation Exception Information: ", exc_info=True)
            return False

    def __getitem__(self, item):
        if item in self.FILE_STRUCTURE:
            var_name = self.FILE_STRUCTURE[item][0]
            nc_var = self.nc_obj.variables[var_name]
            return nc_var
        return self.nc_obj.variables[item]

    def get_fill_value(self, item):
        fill_value = None
        if item in self.FILE_STRUCTURE:
            var_name = self.FILE_STRUCTURE[item][0]
            fill_attr_name = self.FILE_STRUCTURE[item][2]
            if fill_attr_name:
                fill_value = getattr(self.nc_obj.variables[var_name], fill_attr_name)
        if fill_value is None:
            fill_value = getattr(self.nc_obj, self.GLOBAL_FILL_ATTR_NAME, None)

        LOG.debug("File fill value for '%s' is '%f'", item, float(fill_value))
        return fill_value

    def get_scale_value(self, item):
        scale_value = None
        if item in self.FILE_STRUCTURE:
            var_name = self.FILE_STRUCTURE[item][0]
            scale_attr_name = self.FILE_STRUCTURE[item][1]
            if scale_attr_name:
                scale_value = float(getattr(self.nc_obj.variables[var_name], scale_attr_name))
                LOG.debug("File scale value for '%s' is '%f'", item, float(scale_value))
        return scale_value

    def filter_by_frequency(self, item, arr, freq):
        freq_var = self[FREQ_VAR]
        freq_idx = numpy.nonzero(freq_var[:] == freq)[0]
        if freq_idx:
            freq_idx = freq_idx[0]
        else:
            LOG.error("Frequency %f for variable %s does not exist" % (freq, item))
            raise ValueError("Frequency %f for variable %s does not exist" % (freq, item))

        freq_dim_idx = self[item].dimensions.index(freq_var.dimensions[0])
        idx_obj = [slice(x) for x in arr.shape]
        idx_obj[freq_dim_idx] = freq_idx
        return arr[idx_obj]

    def get_swath_data(self, item, dtype=numpy.float32, fill=numpy.nan):
        """Get swath data from the file. Usually requires special processing.
        """
        var_data = self[item][:].astype(dtype)
        freq = self.FILE_STRUCTURE[item][3]
        if freq:
            var_data = self.filter_by_frequency(item, var_data, freq)

        file_fill = self.get_fill_value(item)
        file_scale = self.get_scale_value(item)

        if file_scale:
            var_data = var_data.astype(dtype) / file_scale
        if file_fill:
            var_data[var_data == file_fill] = fill

        return var_data

    def _compare(self, other, method):
        try:
            return method(self.begin_time, other.start_time)
        except AttributeError:
            raise NotImplemented

    def __lt__(self, other):
        return self._compare(other, lambda s, o: s < o)

    def __le__(self, other):
        return self._compare(other, lambda s, o: s <= o)

    def __eq__(self, other):
        return self._compare(other, lambda s, o: s == o)

    def __ge__(self, other):
        return self._compare(other, lambda s, o: s >= o)

    def __gt__(self, other):
        return self._compare(other, lambda s, o: s > o)

    def __ne__(self, other):
        return self._compare(other, lambda s, o: s != o)


class MIRSMultiReader(object):
    SINGLE_FILE_CLASS = MIRSFileReader
    FILE_TYPE = SINGLE_FILE_CLASS.FILE_TYPE

    def __init__(self, filenames=None):
        self.file_readers = []
        self._files_finalized = False
        if filenames:
            self.add_files(filenames)
            self.finalize_files()

    def __len__(self):
        return len(self.file_readers)

    @classmethod
    def handles_file(cls, fn_or_nc_obj):
        return cls.SINGLE_FILE_CLASS.handles_file(fn_or_nc_obj)

    def add_file(self, fn):
        if self._files_finalized:
            LOG.error("File reader has been finalized and no more files can be added")
            raise RuntimeError("File reader has been finalized and no more files can be added")
        self.file_readers.append(self.SINGLE_FILE_CLASS(fn))

    def add_files(self, filenames):
        for fn in filenames:
            self.add_file(fn)

    def finalize_files(self):
        self.file_readers = sorted(self.file_readers)
        self._files_finalized = True

    def write_var_to_flat_binary(self, item, filename, dtype=numpy.float32):
        """Write the data from multiple files to one flat binary file.

        :param item: Variable name to retrieve
        :param filename: Filename filename if the file should follow traditional FBF naming conventions
        """
        LOG.info("Writing binary data for %s to file %s", item, filename)
        with open(filename, "w") as file_obj:
            file_appender = FileAppender(file_obj, dtype)
            for file_reader in self.file_readers:
                single_array = file_reader.get_swath_data(item)
                file_appender.append(single_array)

        return file_appender.shape

    @property
    def satellite(self):
        return self.file_readers[0].satellite

    @property
    def instrument(self):
        return self.file_readers[0].instrument

    @property
    def begin_time(self):
        return self.file_readers[0].begin_time

    @property
    def end_time(self):
        return self.file_readers[-1].end_time

    @property
    def x_res(self):
        return self.file_readers[0].x_res

    @property
    def y_res(self):
        return self.file_readers[0].y_res

    @property
    def filepaths(self):
        return [fr.filepath for fr in self.file_readers]


FILE_CLASSES = {
    FT_IMG: MIRSMultiReader,
}


def get_file_type(filepath):
    LOG.debug("Checking file type for %s", filepath)
    if not filepath.endswith(".nc"):
        return None

    nc_obj = Dataset(filepath, "r")
    for file_kind, file_class in FILE_CLASSES.items():
        if file_class.handles_file(nc_obj):
            return file_kind

    LOG.info("File doesn't match any known file types: %s", filepath)
    return None


class Frontend(object):
    """Polar2Grid Frontend object for handling MIRS files.
    """
    def __init__(self, search_paths=None, **kwargs):
        super(Frontend, self).__init__(**kwargs)
        if not search_paths:
            LOG.info("No files or paths provided as input, will search the current directory...")
            search_paths = ['.']
        self.recognized_files = {}
        for file_kind, filepath in self.find_all_files(search_paths):
            if file_kind not in self.recognized_files:
                self.recognized_files[file_kind] = []
            self.recognized_files[file_kind].append(filepath)
        if not self.recognized_files:
            LOG.error("No useable files provided or found")
            raise RuntimeError("No useable files provided or found")

    def find_all_files(self, search_paths):
        for p in search_paths:
            if os.path.isdir(p):
                LOG.debug("Searching '%s' for useful files", p)
                for fn in os.listdir(p):
                    fp = os.path.join(p, fn)
                    file_type = get_file_type(fp)
                    if file_type is not None:
                        LOG.debug("Recognize file %s as file type %s", fp, file_type)
                        yield (file_type, os.path.realpath(fp))
            elif os.path.isfile(p):
                file_type = get_file_type(p)
                if file_type is not None:
                    LOG.debug("Recognize file %s as file type %s", p, file_type)
                    yield (file_type, os.path.realpath(p))
                else:
                    LOG.error("File is not a valid MIRS file: %s", p)
            else:
                LOG.error("File or directory does not exist: %s", p)

    @property
    def available_product_names(self):
        # Right now there is only one type of file that has all products in it, so all products are available
        # in the future this might have to change
        return [k for k, v in PRODUCTS.items() if not v.dependencies and not v.is_geoproduct]

    @property
    def all_product_names(self):
        return PRODUCTS.keys()

    def _create_raw_swath_object(self, product_name, file_readers, products_created):
        product_def = PRODUCTS[product_name]
        file_reader = file_readers[product_def.file_type]
        filename = product_name + ".dat"
        # TODO: Use dtype somehow
        shape = file_reader.write_var_to_flat_binary(product_def.file_key, filename)
        lat_product = products_created.get(PRODUCT_LATITUDE, None)
        lon_product = products_created.get(PRODUCT_LONGITUDE, None)
        dtype_str = numpy_to_dtype(numpy.float32)
        if product_name in [PRODUCT_LATITUDE, PRODUCT_LONGITUDE]:
            lat_product = None
            lon_product = None
        one_swath = meta.SwathProduct(
            product_name=product_name, description=product_def.description, units=product_def.units,
            satellite=file_reader.satellite, instrument=file_reader.instrument,
            begin_time=file_reader.begin_time, end_time=file_reader.end_time,
            longitude=lon_product, latitude=lat_product, fill_value=numpy.nan,
            swath_rows=shape[0], swath_cols=shape[1], data_type=dtype_str, swath_data=filename,
            source_filenames=file_reader.filepaths, data_kind=product_def.data_kind, rows_per_scan=0,
            x_res=file_reader.x_res, y_res=file_reader.y_res,
        )
        return one_swath

    def create_scene(self, products=None, nprocs=1):
        if nprocs != 1:
            raise NotImplementedError("The MIRS frontend does not support multiple processes yet")
        if products is None:
            products = self.available_product_names
        products = list(set(products))
        LOG.debug("Extracting data to create the following products:\n\t%s", "\n\t".join(products))

        scene = meta.SwathScene()

        # Figure out any dependencies
        raw_products = []
        for product_name in products:
            if PRODUCTS[product_name].dependencies:
                raise NotImplementedError("Don't know how to handle products dependent on other products")
            raw_products.append(product_name)

        # Load files
        file_readers = {}
        for file_type, filepaths in self.recognized_files.items():
            file_reader_class = FILE_CLASSES[file_type]
            file_reader = file_reader_class(filenames=filepaths)
            if len(file_reader):
                file_readers[file_reader.FILE_TYPE] = file_reader

        # Load geographic products - every product needs a geo-product
        products_created = {}
        for geo_product in [PRODUCT_LATITUDE, PRODUCT_LONGITUDE]:
            one_swath = self._create_raw_swath_object(geo_product, file_readers, products_created)
            products_created[geo_product] = one_swath
            if geo_product in raw_products:
                # only process the geolocation product if the user requested it that way
                scene[geo_product] = one_swath

        # Load raw products
        for raw_product in raw_products:
            if raw_product not in products_created:
                one_swath = self._create_raw_swath_object(raw_product, file_readers, products_created)
                products_created[raw_product] = one_swath
                scene[raw_product] = one_swath

        return scene


def add_frontend_argument_groups(parser):
    """Add command line arguments to an existing parser.

    :returns: list of group titles added
    """
    group_title = "frontend_init"
    group = parser.add_argument_group(title=group_title, description="swath extraction initialization options")
    group.add_argument("--list-products", dest="list_products", action="store_true",
                        help="List available frontend products")
    group_title = "frontend_create_scene"
    group = parser.add_argument_group(title=group_title, description="swath extraction options")
    group.add_argument("-p", "--products", dest="products", nargs="*", default=None,
                       help="Specify frontend products to process")
    return ["frontend_init", "frontend_create_scene"]


def main():
    from polar2grid.core.glue_utils import create_basic_parser, setup_logging, create_exc_handler
    parser = create_basic_parser(description="Extract image data from MIRS files and print JSON scene dictionary")
    subgroup_titles = add_frontend_argument_groups(parser)
    parser.add_argument('-f', dest='data_files', nargs="+", default=[],
                        help="List of one or more data files")
    parser.add_argument('-d', dest='data_dirs', nargs="+", default=[],
                        help="Data directories to look for input data files")
    args = parser.parse_args(subgroup_titles=subgroup_titles)

    levels = [logging.ERROR, logging.WARN, logging.INFO, logging.DEBUG]
    setup_logging(console_level=levels[min(3, args.verbosity)], log_filename=args.log_fn)
    sys.excepthook = create_exc_handler(LOG.name)
    LOG.debug("Starting script with arguments: %s", " ".join(sys.argv))

    list_products = args.subgroup_args["frontend_init"].pop("list_products")
    f = Frontend(args.data_files + args.data_dirs, **args.subgroup_args["frontend_init"])

    if list_products:
        print("\n".join(f.available_product_names))
        return 0

    scene = f.create_scene(**args.subgroup_args["frontend_create_scene"])
    print(scene.dumps(persist=True))
    return 0

if __name__ == "__main__":
    sys.exit(main())