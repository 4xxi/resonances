from math import radians
from typing import List, Iterable, Tuple, Dict

import numpy as np
import os
from abc import abstractmethod

from resonances.entities.resonance.twobodyresonance import ResonanceMixin

from resonances.entities.body import LONG
from resonances.entities.body import PERI
from resonances.shortcuts import cutoff_angle
from .collection import OrbitalElementSet
from .collection import OrbitalElementSetCollection
import pandas as pd

SMALL_BODY = 'small_body'
BIG_BODIES = 'big_bodies'
HEADER_LINE_COUNT = 4


class _AggregatedElements:
    def __init__(self, small_body: OrbitalElementSet,
                 big_bodies: List[OrbitalElementSet]):
        self._big_bodies = big_bodies
        self._small_body = small_body

    @property
    def big_bodies(self) -> List[OrbitalElementSet]:
        return self._big_bodies

    @property
    def small_body(self) -> OrbitalElementSet:
        return self._small_body


class ElementCountException(Exception):
    pass


class PhaseCountException(Exception):
    pass


class IOrbitalElementSetFacade(object):
    """
    General class that gives interface for representation set of orbital elements.
    """

    def __init__(self, orbital_element_sets: List[OrbitalElementSetCollection]):
        """
        :param orbital_element_sets: object
        :return:
        """
        self._orbital_element_sets = orbital_element_sets
        if len(self._orbital_element_sets) == 1:
            return
        for i in range(1, len(orbital_element_sets)):
            first_elems_len = len(orbital_element_sets[i - 1])
            second_elems_len = len(orbital_element_sets[i])
            if not (first_elems_len == second_elems_len):
                raise ElementCountException(
                    'count of first body elements: %i not equal second body: %i' %
                    (first_elems_len, second_elems_len)
                )

    def _get_body_orbital_elements2(self, aei_data: pd.DataFrame) \
            -> Iterable[List[OrbitalElementSet]]:
        # -> Iterable[_AggregatedElements]:
        """Build orbital elements of bodies from data of the .aei file.
        :return: generator of dictionaries, contains set of orbital elements
        for two planets and asteroid.
        """
        # for i, line in enumerate(aei_data):
        for i in range(aei_data.shape[0]):
            # if i < HEADER_LINE_COUNT:
            #     continue

            # index = i - HEADER_LINE_COUNT
            var = [x[i] for x in self._orbital_element_sets]
            # yield _AggregatedElements(OrbitalElementSet(line), var)
            yield var

    def _get_body_orbital_elements(self, aei_data: List[str]) \
            -> Iterable[_AggregatedElements]:
        """Build orbital elements of bodies from data of the .aei file.
        :return: generator of dictionaries, contains set of orbital elements
        for two planets and asteroid.
        """
        for i, line in enumerate(aei_data):
            if i < HEADER_LINE_COUNT:
                continue

            index = i - HEADER_LINE_COUNT
            var = [x[index] for x in self._orbital_element_sets]
            yield _AggregatedElements(OrbitalElementSet(line), var)

    def write_to_resfile(self, res_filepath: str, aei_data: List[str]):
        """Saves data, returned by method get_elements to res file.
        :param res_filepath: path of file for saving
        :param aei_data: data of aei file. It will be user for building
        instances of internal class, that represents set of orbital elemetns
        in res file format.
        """
        if not os.path.exists(os.path.dirname(res_filepath)):
            os.makedirs(os.path.dirname(res_filepath))
        with open(res_filepath, 'w') as resonance_file:
            for item in self.get_elements(aei_data):
                resonance_file.write(item)

    @abstractmethod
    def get_elements(self, aei_data: List[str]) -> Iterable[str]:
        pass


class ComputedOrbitalElementSetFacade(IOrbitalElementSetFacade):
    """Facade of set of the orbital elements, that doesn't compute resonant
    phase. It represents elements by pointed sets of orbital elements of the
    planets and resonant phases.
    """

    def __init__(self, orbital_element_sets: List[OrbitalElementSetCollection],
                 resonant_phases: List[float]):
        """
        :param orbital_element_sets:
        :param resonant_phases:
        :return:
        """
        super(ComputedOrbitalElementSetFacade, self).__init__(orbital_element_sets)
        second_elems_len = len(orbital_element_sets[0])
        if not (len(resonant_phases) == second_elems_len):
            raise PhaseCountException(
                'Number of resonant phases %i is not equal %i' %
                (len(resonant_phases), second_elems_len)
            )
        self._resonant_phases = resonant_phases

    def get_elements(self, aei_data: List[str]) -> Iterable[str]:
        """
        :param aei_data:
        :return:
        """
        for i, orbital_elements in enumerate(self._get_body_orbital_elements(aei_data)):
            resonant_phase = self._resonant_phases[i]
            resonance_data = "%f %f %s %s\n" % (
                orbital_elements.small_body.time, resonant_phase,
                orbital_elements.small_body.serialize_as_asteroid(),
                ' '.join([x.serialize_as_planet() for x in orbital_elements.big_bodies])
            )
            yield resonance_data


class AsteroidElementCountException(Exception):
    pass


class ResonanceOrbitalElementSetFacade(IOrbitalElementSetFacade):
    """Facade of set of the orbital elements, that computes resonant phase for
    pointed resonance. It represents elements by pointed sets of orbital
    elements of the planets and computed resonant phases.
    """

    def __init__(self, orbital_element_sets: List[OrbitalElementSetCollection],
                 resonance: ResonanceMixin):
        """
        :param orbital_element_sets:
        :param resonance:
        :return:
        """
        super(ResonanceOrbitalElementSetFacade, self).__init__(orbital_element_sets)
        self._resonance = resonance

    def _compute_phases(self, elems: List[List[OrbitalElementSet]],
                        small_body_m_l: np.array, small_body_p_l: np.array) -> np.array:
        phases = np.zeros(len(elems))
        for i in range(len(elems[0])):
            m_longs = np.array([x[i].m_longitude for x in elems])
            p_longs = np.array([x[i].p_longitude for x in elems])
            big_body = self._resonance.get_big_bodies()[i]

            summand1 = m_longs * big_body.longitude_coeff
            summand2 = p_longs * big_body.perihelion_longitude_coeff
            phases += summand1 + summand2

        small_body = self._resonance.small_body
        phases += (
            small_body_m_l * small_body.longitude_coeff +
            small_body_p_l * small_body.perihelion_longitude_coeff
        )

        return [cutoff_angle(x) for x in phases]

    def _get_asteroid_pars(self, aei_data: List[str]):
        times = []
        p_longs = []
        mean_anomalies = []
        for i, line in enumerate(aei_data):
            if i < HEADER_LINE_COUNT:
                continue

            datas = line.split()
            times.append(float(datas[0]))
            p_longs.append(radians(float(datas[1])))
            mean_anomalies.append(radians(float(datas[2])))
        p_longs = np.array(p_longs)
        mean_anomalies = np.array(mean_anomalies)
        m_longs = p_longs + mean_anomalies
        return m_longs, p_longs, times

# AEI_HEADER = ['Time (years)', 'long', 'M', 'a', 'e', 'i', 'peri', 'node', 'mass']

    def _get_longitutes(self, aei_data: pd.DataFrame):
        times = aei_data['Time (years)']
        p_longs = np.radians(aei_data['long'])
        mean_anomalies = np.radians(aei_data['M'])
        m_longs = p_longs + mean_anomalies
        return m_longs, p_longs, times

    def _validate_asteroid_orbital_elements(self, from_aei_data: pd.DataFrame):
        planets_elements_count = len(self._orbital_element_sets[0])
        asteroid_elements_count = from_aei_data.shape[0]
        if planets_elements_count != asteroid_elements_count:
            raise AsteroidElementCountException(
                'Number of elements (%i) for asteroid in aei file is not '
                'equal to number of elements (%i) for planets.' %
                (planets_elements_count, asteroid_elements_count))

    def get_resonant_phases(self, aei_data: pd.DataFrame) -> Iterable[Tuple[float, float]]:
        self._validate_asteroid_orbital_elements(aei_data)
        m_longs, p_longs, times = self._get_longitutes(aei_data)
        elems = [x for x in self._get_body_orbital_elements2(aei_data)]
        if not elems:
            return []
        phases = self._compute_phases(elems, m_longs, p_longs)
        return [(x, y) for x, y in zip(times, phases)]

    def get_elements(self, aei_data: List[str]) -> Iterable[str]:
        """
        :param aei_data:
        :return:
        """
        for orbital_elements in self._get_body_orbital_elements(aei_data):
            small_body = orbital_elements.small_body
            resonant_phase = self._resonance.compute_resonant_phase(
                _get_longitudes(orbital_elements.big_bodies + [small_body]))
            resonant_phase = cutoff_angle(resonant_phase)
            resonance_data = "%f %f %s %s\n" % (
                orbital_elements.small_body.time, resonant_phase,
                orbital_elements.small_body.serialize_as_asteroid(),
                ' '.join([x.serialize_as_planet() for x in orbital_elements.big_bodies])
            )
            yield resonance_data


def _get_longitudes(from_elem_sets: List[OrbitalElementSet]) -> List[Dict[str, float]]:
    res = []
    for elems in from_elem_sets:
        res.append({
            LONG: elems.m_longitude,
            PERI: elems.p_longitude
        })
    return res
