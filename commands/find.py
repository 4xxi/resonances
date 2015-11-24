import logging
import sys
import os
from os.path import join as opjoin
from typing import List, Tuple, Iterable
from catalog import find_by_number
from integrator import ResonanceOrbitalElementSet
from settings import Config
from storage import ResonanceDatabase
from storage.resonance_archive import extract
from utils.series import find_circulation
from entities import build_resonance, Libration
from entities import ThreeBodyResonance

CONFIG = Config.get_params()
PROJECT_DIR = Config.get_project_dir()
X_STOP = CONFIG['gnuplot']['x_stop']
AXIS_SWING = CONFIG['resonance']['axis_error']
RESONANCE_TABLE_FILE = CONFIG['resonance_table']['file']
RESONANCE_FILEPATH = opjoin(PROJECT_DIR, 'axis', RESONANCE_TABLE_FILE)
BODIES_COUNTER = CONFIG['integrator']['number_of_bodies']
OUTPUT_ANGLE = CONFIG['output']['angle']
BODY1 = CONFIG['resonance']['bodies'][0]
BODY2 = CONFIG['resonance']['bodies'][1]


def _get_resonances(by_asteroid_axis: float, with_swing: float) \
        -> List[ThreeBodyResonance]:
    res = []
    try:
        with open(RESONANCE_FILEPATH) as resonance_file:
            for line in resonance_file:
                line_data = line.split()
                resonance = build_resonance(line_data)
                if abs(resonance.asteroid_axis - by_asteroid_axis) <= with_swing:
                    res.append(resonance)
    except FileNotFoundError:
        logging.error('File %s not found. Try command resonance_table.',
                      RESONANCE_FILEPATH)
        sys.exit(1)

    return res


def _find_resonance_with_min_axis(by_axis: float, with_swing: float = 0.0001) \
        -> ThreeBodyResonance:
    resonances = _get_resonances(by_axis, with_swing)
    index_of_min_axis = 0

    def _delta(of_resonance: ThreeBodyResonance) -> float:
        return of_resonance.asteroid_axis - by_axis

    for i, resonance in enumerate(resonances):
        if _delta(resonance) < _delta(resonances[index_of_min_axis]):
            index_of_min_axis = i

    return resonances[index_of_min_axis]


def _find_resonances(start: int, stop: int) -> Iterable[Tuple[int, ThreeBodyResonance]]:
    """Find resonances from /axis/resonances by asteroid axis. Currently
    described by 7 items list of floats. 6 is integers satisfying
    D'Alembert rule. First 3 for longitutes, and second 3 for longitutes
    perihilion. Seventh value is asteroid axis.

    :param stop:
    :param start:
    :return:
    """

    delta = stop - start
    for i in range(delta + 1):
        asteroid_num = start + i
        asteroid_parameters = find_by_number(asteroid_num)
        for resonances in _get_resonances(asteroid_parameters[1], AXIS_SWING):
            if resonances:
                yield asteroid_num, resonances


def _get_orbitalelements_filepaths(body_number: int) -> Tuple[str, str, str]:
    mercury_dir = opjoin(PROJECT_DIR, CONFIG['integrator']['dir'])
    mercury_planet_dir = mercury_dir

    body_number_start = body_number - body_number % 100
    body_number_stop = body_number_start + BODIES_COUNTER
    aei_dir = opjoin(
        PROJECT_DIR, CONFIG['export']['aei_dir'],
        '%i-%i' % (body_number_start, body_number_stop), 'aei'
    )
    aei_filepath = opjoin(aei_dir, 'A%i.aei' % body_number)
    if os.path.exists(aei_filepath):
        mercury_dir = aei_dir
        mercury_planet_dir = opjoin(
            PROJECT_DIR, CONFIG['export']['aei_dir'], 'Planets'
        )

    smallbody_filepath = opjoin(mercury_dir, 'A%i.aei' % body_number)
    firstbody_filepath = opjoin(mercury_planet_dir, '%s.aei' % BODY1)
    secondbody_filepath = opjoin(mercury_planet_dir, '%s.aei' % BODY2)

    return smallbody_filepath, firstbody_filepath, secondbody_filepath


def find(start: int, stop: int, is_current: bool = False):
    """Find all possible resonances for all asteroids from start to stop.

    :param is_current:
    :param stop:
    :param start:
    :return:
    """
    rdb = ResonanceDatabase('export/full.db')
    if not is_current:
        try:
            extract(start)
        except FileNotFoundError as exc:
            logging.info('Archive %s not found. Try command \'package\'',
                         exc.filename)

    for asteroid_num, resonance in _find_resonances(start, stop):
        smallbody_filepath, firstbody_filepath, secondbody_filepath \
            = _get_orbitalelements_filepaths(asteroid_num)
        resonance_filepath = opjoin(PROJECT_DIR, OUTPUT_ANGLE,
                                    'A%i.res' % asteroid_num)
        logging.debug("Check asteroid %i", asteroid_num)
        orbital_elem_set = ResonanceOrbitalElementSet(
            resonance, firstbody_filepath, secondbody_filepath)

        if not os.path.exists(os.path.dirname(resonance_filepath)):
            os.makedirs(os.path.dirname(resonance_filepath))
        with open(resonance_filepath, 'w+') as resonance_file:
            for item in orbital_elem_set.get_elements(smallbody_filepath):
                resonance_file.write(item)

        circulations = find_circulation(resonance_filepath, False)
        libration = Libration(asteroid_num, resonance, circulations, X_STOP)

        if not libration.is_pure:
            if libration.is_apocentric:
                if libration.percentage:
                    logging.info('A%i, %s, resonance = %s', asteroid_num,
                                 str(libration), str(resonance))
                    rdb.add_string(libration.as_apocentric())
                else:
                    logging.debug(
                        'A%i, NO RESONANCE, resonance = %s, max = %f',
                        asteroid_num, str(resonance), libration.max_diff
                    )
        else:
            logging.info('A%i, pure resonance %s', asteroid_num, str(resonance))
            rdb.add_string(libration.as_pure())

        circulations = find_circulation(resonance_filepath, True)
        libration = Libration(asteroid_num, resonance, circulations, X_STOP)
        if libration.is_pure:
            logging.info('A%i, pure apocentric resonance %s', asteroid_num,
                         str(resonance))
            rdb.add_string(libration.as_pure_apocentric())