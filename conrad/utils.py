# -*- coding: utf-8 -*-
"""Common utility functions.
"""
import collections
import logging
import os

import numpy as np
import typhon
from netCDF4 import Dataset

from conrad import constants


__all__ = [
    'append_timestep_netcdf',
    'create_relative_humidity_profile',
    'ensure_decrease',
    'calculate_halflevel_pressure',
    'append_description',
    'refined_pgrid',
    'revcumsum',
    'extract_metadata',
    'radiation_budget',
    'equilibrium_sensitivity',
]

logger = logging.getLogger(__name__)


def append_timestep_netcdf(filename, data, timestamp):
    """Append a timestep to an existing netCDF4 file.

    Notes:
        The variables to append to have to exist in the netCDF4 file!

    Parameters:
        filename (str): Path to the netCDF4.
        data (dict{ndarray}): Dict-like object containing the data arrays.
            The key is the variable name and the value is an ``ndarray``, a
            ``pandas.Series`` or an ``xarray.DataArray`` e.g.:
                >>> data = {'T': np.array([290, 295, 300])}

        timestamp (float): Timestamp of values appended.
    """
    # Open netCDF4 file in `append` mode.
    with Dataset(filename, 'a') as nc:
        logging.debug('Append timestep to "{}".'.format(filename))
        t = nc.dimensions['time'].size  # get index to store data.
        nc.variables['time'][t] = timestamp  # append timestamp.

        # Append data for each variable in ``data``.
        for var in data:
            # Append variable if it has a `time` dimension and is no
            # dimension itself.
            if 'time' in nc[var].dimensions and var not in nc.dimensions:
                # TODO: Find a cleaner way to handle different data dimensions.
                if 'plev' in nc[var].dimensions:
                    if hasattr(data[var], 'values'):
                        nc.variables[var][t, :] = data[var].values
                    else:
                        nc.variables[var][t, :] = data[var]
                else:
                    if hasattr(data[var], 'values'):
                        nc.variables[var][t] = data[var].values
                    else:
                        nc.variables[var][t] = data[var]


def create_relative_humidity_profile(p, rh_s=0.75):
    """Create an exponential relative humidity profile.

    Parameters:
        p (ndarray): Pressure.
        rh_s (float): Relative humidity at first pressure level.

    Returns:
        ndarray: Relative humidtiy."""
    rh = rh_s / (np.exp(1) - 1) * (np.exp(p / p[0]) - 1)
    return np.round(rh, decimals=4)


def ensure_decrease(array):
    """Ensure that a given array is decreasing.

    Parameters:
        array (ndarray): Input array.

    Returns:
        ndarray: Monotonously decreasing array.
    """
    for i in range(1, len(array)):
        if array[i] > array[i-1]:
            array[i] = array[i-1]
    return array


def calculate_halflevel_pressure(fulllevels):
    """Returns the linear interpolated halflevels for given array.

    Parameters:
        fulllevels (ndarray): Pressure at fullevels.

    Returns:
        ndarray: Coordinates at halflevel.

    """
    inter = (fulllevels[1:] + fulllevels[:-1]) / 2
    bottom = fulllevels[0] - 0.5 * (fulllevels[1] - fulllevels[0])
    top = 0
    return np.hstack((bottom, inter, top))


def append_description(dataset, description=None):
    """Append variable attributes to a given dataset.

    Parameters:
          dataset (xarray.Dataset): Dataset including variables to describe.
          description (dict): Dictionary containing variable descriptions.
            The keys are the variable keys used in the Dataset.
            The values are dictionaries themselves containing attributes
            and their names as keys, e.g.:
                desc = {'T': {'units': 'K', 'standard_name': 'temperature'}}
    """
    if description is None:
        description = constants.variable_description

    for key in dataset.keys():
        if key in description:
            dataset[key].attrs = constants.variable_description[key]


def refined_pgrid(start, stop, num=200, threshold=100e2):
    """Create a pressure grid with two spacing regimes.

    This functions creates a pressure grid with two different spacing regimes:
    The atmosphere is split into two parts at a given threshold. For both
    parts, a logarithmic pressure grid with the same amount of points is
    created. This allows to force more gridpoints into one of the parts.

    Parameters:
        start (float): Pressure at lowest atmosphere layer.
        stop (float): Pressure at highest atmosphere layer.
        num (int): Number of pressure layers.
        threshold (float): Pressure layer at which to swich spacing.

    Returns:
        ndarray: Pressure grid.
    """
    # Divide the number of gridpoints evenly across lower and upper atmosphere.
    nbottom, ntop = np.ceil(num / 2), np.floor(num / 2)

    # Create a logarithmic spaced pressure grid for the lower atmosphere.
    # The endpoint (`threshold`) is excluded to avoid double entries.
    p_tropo = typhon.math.nlogspace(start, threshold, nbottom + 1)[:-1]

    # Create a logarithmic spacing pressure grid for the upper atmosphere.
    p_strato = typhon.math.nlogspace(threshold, stop, ntop)

    return np.hstack([p_tropo, p_strato])


def revcumsum(x):
    """Returns the reversed cumulative sum of an array.

    Paramters:
        x (ndarray): Array.

    Returns:
        ndarray: Reversed cumulative sum.

    Example:
        >>> revcumsum(np.array([0, 1, 2, 3, 4]))
        array([10, 10, 9, 7, 4])
    """
    return x[::-1].cumsum()[::-1]


def extract_metadata(filepath, delimiter='_'):
    """Extract meta information for simulation from filename.

    Naming convention for the function to work properly:
        /path/to/output/{season}_{experiment}_{scale}.nc

    Additional information may be appended:
        /path/to/output/{season}_{experiment}_{scale}_{extra_info}.nc

    Parameters:
        filepath (str): Path to output file.
        delimiter (str): Delimiter used to separate meat information.

    Returns:
        collections.namedtuple: Extracted information on `season`,
            `experiment`, `scale` and additional `extra` information.

    Examples:
        >>> extract_metadata('results/tropical_nlayers_100.nc')
        Fileinformation(season='tropical', experiment='nlayers',
                        scale='100', extra='')

        >>> extract_metadata('results/tropical_nlayers_100_fast.nc')
        Fileinformation(season='tropical', experiment='nlayers',
                        scale='100', extra='fast')
    """
    # Trim parentdir and extension from given path. This simplifies the
    # extraction of the wanted information in the next steps.
    filename = os.path.splitext(os.path.basename(filepath))[0]

    # Extract information on season, experiment and scale from filename.
    # Optional remaining fields are collected as "extra" information.
    season, experiment, scale, *extra = filename.split(delimiter)

    # Define namedtuple to access results more conveniently.
    nt = collections.namedtuple(
        typename='Fileinformation',
        field_names=['season', 'experiment', 'scale', 'extra'],
    )

    return nt._make((season, experiment, scale, delimiter.join(extra)))


def radiation_budget(lw_flxu, lw_flxd, sw_flxu, sw_flxd):
    """Calculate the net radiation budget.

    Notes:
          Positive values imply a net downward flux.

    Parameters:
        lw_flxu (ndarray): Longwave upward flux [W/m^2].
        lw_flxd (ndarray): Longwave downward flux [W/m^2].
        sw_flxu (ndarray): Shortwave upward flux [W/m^2].
        sw_flxd (ndarray): Shortwave downward flux [W/m^2].

    Returns:
        ndarray: Net radiation budget [W/m^2].
    """
    return ((sw_flxd + lw_flxd) - (sw_flxu + lw_flxu))


def equilibrium_sensitivity(temperature, forcing):
    """Calculate the equilibrium climate sensitivity.

    The equilibrium climate sensitivity is given by the temperature difference
    between the first and last timestep divided by the initial radiative
    forcing.

    Parameters:
          temperature (ndarray): Surface temperature [K].
          forcing (ndarray): Radiative forcing [W/m^2].
    Returns:
          float, float: Climate sensitivity [K / (W/m^2)],
            initial radiative forcing [W/m^2].

    Examples:
        >>> temperature = np.linspace(300, 304, 25)
        >>> forcing = np.linspace(3.7, 0., temperature.size)
        >>> equilibrium_sensitivity(temperature, forcing)
        (1.0810810810810809, 3.7000000000000002)
    """
    return (temperature[-1] - temperature[0]) / forcing[0], forcing[0]