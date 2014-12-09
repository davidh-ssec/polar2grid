#!/usr/bin/env python
# encoding: utf-8
# Copyright (C) 2014 Space Science and Engineering Center (SSEC),
# University of Wisconsin-Madison.
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# This file is part of the polar2grid software package. Polar2grid takes
# satellite observation data, remaps it, and writes it to a file format for
# input into another program.
# Documentation: http://www.ssec.wisc.edu/software/polar2grid/
#
#     Written by David Hoese    December 2014
#     University of Wisconsin-Madison
#     Space Science and Engineering Center
#     1225 West Dayton Street
#     Madison, WI  53706
#     david.hoese@ssec.wisc.edu
"""Python wrapper around binary crefl calls.

:author:       David Hoese (davidh)
:contact:      david.hoese@ssec.wisc.edu
:organization: Space Science and Engineering Center (SSEC)
:copyright:    Copyright (c) 2014 University of Wisconsin SSEC. All rights reserved.
:date:         Dec 2014
:license:      GNU GPLv3

"""
__docformat__ = "restructuredtext en"

import os
import sys
from subprocess import check_output, CalledProcessError, STDOUT
from itertools import izip
import logging

LOG = logging.getLogger(__name__)
# executable names
H5SDS_TRANSFER_RENAME_NAME = os.environ.get("P2G_H5SDS_TRANSFER_RENAME", "h5SDS_transfer_rename")
CVIIRS_NAME = os.environ.get("P2G_CVIIRS_NAME", "cviirs")
CREFL_NAME = os.environ.get("P2G_CREFL_NAME", "crefl.1.7.1")
# Where the CMGDEM.hdf file is
# Defaults to: /path/to/polar2grid/bin
cviirs_path = os.path.realpath(os.path.join(os.path.dirname(sys.executable), "../../bin"))
CMGDEM_PATH = os.environ.get("P2G_CVIIRS_ANCPATH", os.environ.get("ANCPATH", cviirs_path))
TBASE_PATH = os.environ.get("P2G_CMODIS_ANCPATH", os.environ.get("ANCPATH", cviirs_path))


def run_hdf5_rename(input_filename, output_filename, input_variable, output_variable=None):
    output_variable = output_variable if output_variable else input_variable

    try:
        args = [H5SDS_TRANSFER_RENAME_NAME, input_filename, output_filename, input_variable, output_variable]
        args = [str(a) for a in args]
        LOG.debug("Running h5SDS_transfer_rename with '%s'" % " ".join(args))
        transfer_output = check_output(args, stderr=STDOUT)
        LOG.debug("h5SDS_transfer_rename output:\n%s", transfer_output)

        # Check to make sure the HDF4 file actually exists now
        if not os.path.exists(output_filename):
            LOG.error("Couldn't find new HDF4 output file '%s'" % output_filename)
            raise RuntimeError("Couldn't find HDF4 output file '%s'" % output_filename)
    except CalledProcessError as e:
        LOG.debug("h5SDS_transfer_rename output:\n%s", e.output, exc_info=True)
        LOG.error("Error running h5SDS_transfer_rename")
        raise ValueError("h5SDS_transfer_rename failed")
    except OSError:
        LOG.error("Couldn't find '%s' command in PATH", H5SDS_TRANSFER_RENAME_NAME)
        raise ValueError("h5SDS_transfer_rename was not found your PATH")

    return output_filename


def _run_cviirs(output_filename, input_filenames, bands=None, overwrite=True, verbose=True, output_500m=False, output_1km=False):
    """Run cviirs on one set of file (one granule's worth of time)

    Essentially a replacement for `run_viirs_crefl.sh`.
    """
    args = [CVIIRS_NAME]
    if bands:
        if isinstance(bands, (str, int)):
            bands = [bands]
        bands = ",".join([str(x) for x in bands])
        args.append("--bands=%s" % (bands,))
    if not output_500m and not output_1km:
        raise ValueError("Must either specify output_500m or output_1km")
    if output_500m:
        args.append("--500m")
    if output_1km:
        args.append("--1km")
    if overwrite:
        args.append("--overwrite")
    if verbose:
        args.append("--verbose")
    args.append("--of=%s" % (output_filename,))
    if isinstance(input_filenames, str):
        input_filenames = [input_filenames]
    args.extend(input_filenames)

    try:
        args = [str(a) for a in args]
        LOG.debug("Running cviirs with '%s'" % " ".join(args))
        os.environ["ANCPATH"] = CMGDEM_PATH
        transfer_output = check_output(args, stderr=STDOUT)
        LOG.debug("cviirs output:\n%s", transfer_output)

        # Check to make sure the HDF4 file actually exists now
        if not os.path.exists(output_filename):
            LOG.error("Couldn't find CREFL HDF4 output file '%s'" % output_filename)
            raise RuntimeError("Couldn't CREFL HDF4 output file '%s'" % output_filename)
    except CalledProcessError as e:
        LOG.debug("cviirs output:\n%s", e.output, exc_info=True)
        LOG.error("Error running cviirs")
        raise ValueError("cviirs failed")
    except OSError:
        LOG.error("Couldn't find '%s' command in PATH", CVIIRS_NAME)
        raise ValueError("cviirs was not found your PATH")

    return output_filename

def run_cviirs(geo_files,
               m05_files=None, m07_files=None, m03_files=None, m04_files=None,
               m08_files=None, m10_files=None, m11_files=None,
               i01_files=None, i02_files=None, i03_files=None, keep_intermediate=False):
    """Run cviirs for multiple granules worth of files.

    Note: cviirs requires a 'CMGDEM.hdf' to be in the same directory as the 'cviirs' executable. The search directory
    can be changed with the 'ANCPATH' environment variable.
    """
    m_files = [m05_files, m07_files, m03_files, m04_files, m08_files, m10_files, m11_files]
    i_files = [i01_files, i02_files, i03_files]
    m_vars = ["Reflectance_Mod_M%d" % (i,) for i in [5, 7, 3, 4, 8, 10, 11]]
    i_vars = ["Reflectance_Img_I%d" % (i,) for i in range(1, 4)]
    m_bands = [str(x) for x in range(1, 8)]
    i_bands = ["8", "9", "10"]
    output_filenames = []
    for idx, geo_file in enumerate(geo_files):
        # transfer HDF5 files to HDF4 versions of themselves because that's how CREFL plays
        svm_temp_file = "NPP_VMAE_L1.hdf"
        svi_temp_file = "NPP_VIAE_L1.hdf"
        output_suffix = "_".join(os.path.basename(geo_file).split("_")[1:5])
        m_output_filename = "CREFLM_%s.hdf" % (output_suffix,)
        i_output_filename = "CREFLI_%s.hdf" % (output_suffix,)
        output_filenames.append(m_output_filename)
        output_filenames.append(i_output_filename)
        try:
            run_hdf5_rename(geo_file, svm_temp_file, "Latitude")
            run_hdf5_rename(geo_file, svm_temp_file, "Longitude")
            run_hdf5_rename(geo_file, svm_temp_file, "SatelliteAzimuthAngle", "SenAziAng_Mod")
            run_hdf5_rename(geo_file, svm_temp_file, "SatelliteZenithAngle", "SenZenAng_Mod")
            run_hdf5_rename(geo_file, svm_temp_file, "SolarZenithAngle", "SolZenAng_Mod")
            run_hdf5_rename(geo_file, svm_temp_file, "SolarAzimuthAngle", "SolAziAng_Mod")

            bands = []
            for m_file_list, m_var, m_band in izip(m_files, m_vars, m_bands):
                if m_files:
                    LOG.debug("Running HDF5 to HDF4 transfer tool for band %s using var %s", m_band, m_var)
                    run_hdf5_rename(m_file_list[idx], svm_temp_file, "Reflectance", m_var)
                    bands.append(m_band)

            # GITCO_npp_d20120225_t1805407_e1807049_b01708_c20120226002721519187_noaa_ops.h5
            # Result: npp_d20120225_t1805407_e1807049
            LOG.info("Running CREFL for M bands")
            _run_cviirs(m_output_filename, [svm_temp_file], bands=bands, output_1km=True)

            bands = []
            for i_file_list, i_var, i_band in izip(i_files, i_vars, i_bands):
                if i_files:
                    LOG.debug("Running HDF5 to HDF4 transfer tool for band %s using var %s", m_band, m_var)
                    run_hdf5_rename(i_file_list[idx], svi_temp_file, "Reflectance", i_var)
                    bands.append(i_band)

            LOG.info("Running CREFL for I bands")
            _run_cviirs(i_output_filename, [svm_temp_file, svi_temp_file], bands=bands, output_500m=True)
        except StandardError:
            LOG.error("Could not create VIIRS CREFL files", exc_info=True)
            LOG.error("Could not create VIIRS CREFL files")
            if os.path.isfile(m_output_filename) and not keep_intermediate:
                LOG.debug("Removing unfinished CREFLM file: %s", m_output_filename)
                os.remove(m_output_filename)
            if os.path.isfile(i_output_filename) and not keep_intermediate:
                LOG.debug("Removing unfinished CREFLI file: %s", i_output_filename)
                os.remove(i_output_filename)
            raise
        finally:
            if os.path.isfile(svm_temp_file) and not keep_intermediate:
                LOG.debug("Removing temporary crefl file: %s", svm_temp_file)
                os.remove(svm_temp_file)
            if os.path.isfile(svi_temp_file) and not keep_intermediate:
                LOG.debug("Removing temporary crefl file: %s", svi_temp_file)
                os.remove(svi_temp_file)

    return output_filenames
