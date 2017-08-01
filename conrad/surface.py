# -*- coding: utf-8 -*-
"""Module containing classes describing different surface models.
"""
import abc
import logging

import numpy as np
from xarray import Dataset, DataArray

from . import (constants, utils)


__all__ = [
    'Surface',
    'SurfaceFixedTemperature',
    'SurfaceNoHeatCapacity',
    'SurfaceHeatCapacity',
]


logger = logging.getLogger()


class Surface(Dataset, metaclass=abc.ABCMeta):
    """Abstract base class to define requirements for surface models."""
    def __init__(self, albedo=0.3, temperature=288., pressure=101325.,
                 height=0.):
        """Initialize a surface model.

        Parameters:
            albedo (float): Surface albedo.
            temperature (float): Surface temperature [K].
            pressure (float): Surface pressure [Pa].
            height (float): Surface height [m].
        """
        super().__init__()
        self['albedo'] = albedo
        self['pressure'] = pressure
        self['time'] = [0]
        self['height'] = height
        self['temperature'] = DataArray(np.array([temperature]),
                                        dims=('time',),
                                        )

        utils.append_description(self)

    @abc.abstractmethod
    def adjust(self, sw_down, sw_up, lw_down, lw_up, timestep):
        """Adjust the surface according to given radiative fluxes.

        Parameters:
            sw_down (float): Shortwave downward flux [W / m**2].
            sw_up (float): Shortwave upward flux [W / m**2].
            lw_down (float): Longwave downward flux [W / m**2].
            lw_up (float): Longwave upward flux [W / m**2].
            timestep (float): Timestep in days.
        """
        pass

    @classmethod
    def from_atmosphere(cls, atmosphere, **kwargs):
        """Initialize a Surface object using the lowest atmosphere layer.

        Parameters:
            atmosphere (conrad.atmosphere.Atmosphere): Atmosphere model.
        """
        # Copy temperature of lowest atmosphere layer.
        t_sfc = atmosphere['T'].values[0, 0]

        # Extrapolate surface pressure from last two atmosphere layers.
        p = atmosphere['plev'].values
        p_sfc = p[0] + 0.5 * (p[0] - p[1])

        # Extrapolate surface pressure from last two atmosphere layers.
        z = atmosphere['z'].values[0, :]
        z_sfc = z[0] + 0.5 * (z[0] - z[1])

        return cls(temperature=t_sfc,
                   pressure=p_sfc,
                   height=z_sfc,
                   **kwargs,
                   )


class SurfaceFixedTemperature(Surface):
    """Surface model with fixed temperature."""
    def adjust(self, *args, **kwargs):
        """Do not adjust anything for fixed temperature surfaces.

        This function takes an arbitrary number of positional arguments and
        keyword arguments and does nothing.

        Notes:
            Dummy function to fulfill abstract class requirements.
        """
        return


class SurfaceNoHeatCapacity(Surface):
    """Surface model with adjustable temperature."""
    def adjust(self, sw_down, sw_up, lw_down, lw_up, timestep):
        """Increase the surface temperature by given surface fluxes.

        Parameters:
            sw_down (float): Shortwave downward flux [W / m**2].
            sw_up (float): Shortwave upward flux [W / m**2].
            lw_down (float): Longwave downward flux [W / m**2].
            lw_up (float): Longwave upward flux [W / m**2].
            timestep (float): Timestep in days.

        Notes:
            The surface is assumed to have no heat capacity.
        """
        net_down_flux = (sw_down - sw_up) + lw_down
        t_new = (net_down_flux / constants.stefan_boltzmann)**0.25

        self['temperature'].values[0] = t_new

        logger.debug(f'Surface temperature: {t_new:.4f} K')


class SurfaceHeatCapacity(Surface):
    """Surface model with adjustable temperature.

    Parameters:
          cp (float): Heat capacity [J kg^-1 K^-1 ].
          rho (float): Soil density [kg m^-3].
          dz (float): Surface thickness [m].
          **kwargs: Additional keyword arguments are passed to `Surface`.
    """
    def __init__(self, *args, cp=1000, rho=1000, dz=100, **kwargs):
        super().__init__(*args, **kwargs)
        self['cp'] = cp
        self['rho'] = rho
        self['dz'] = dz

        utils.append_description(self)

    def adjust(self, sw_down, sw_up, lw_down, lw_up, timestep):
        """Increase the surface temperature by given heatingrate.

        Parameters:
            sw_down (float): Shortwave downward flux [W / m**2].
            sw_up (float): Shortwave upward flux [W / m**2].
            lw_down (float): Longwave downward flux [W / m**2].
            lw_up (float): Longwave upward flux [W / m**2].
            timestep (float): Timestep in days.
        """
        timestep *= 24 * 60 * 60  # Convert timestep to seconds.

        net_flux = (sw_down - sw_up) + (lw_down - lw_up)

        logger.debug(f'Net flux: {net_flux:.2f} W /m^2')

        self['temperature'] += (timestep * net_flux /
                                (self.cp * self.rho * self.dz))

        logger.debug('Surface temperature: '
                     f'{self.temperature.values[0]:.4f} K')
