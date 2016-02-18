import json
import logging
import subprocess
from math import pi
from typing import List

import os
from catalog import find_resonances
from entities import ThreeBodyResonance, Phase
from entities.dbutills import engine, REDIS
from datamining import build_bigbody_elements, ComputedOrbitalElementSetFacade, PhaseCountException
from os.path import join as opjoin
from settings import Config
from utils.shortcuts import cutoff_angle

CONFIG = Config.get_params()
PROJECT_DIR = Config.get_project_dir()
MERCURY_DIR = opjoin(PROJECT_DIR, CONFIG['integrator']['dir'])
BODY1 = CONFIG['resonance']['bodies'][0]
BODY2 = CONFIG['resonance']['bodies'][1]
OUTPUT_IMAGES = opjoin(PROJECT_DIR, CONFIG['output']['images'])
OUTPUT_GNU_PATH = opjoin(PROJECT_DIR, CONFIG['output']['gnuplot'])
OUTPUT_RES_PATH = opjoin(PROJECT_DIR, CONFIG['output']['angle'])
TABLENAME = Phase.__tablename__


def make_plots_from_redis(start: int, stop: int):
    for resonance, aei_data in find_resonances(start, stop):
        phases = [
            json.loads(x.decode('utf-8').replace('\'', '"'))['value']
            for x in REDIS.lrange('%s:%i' % (TABLENAME, resonance.id), 0, -1)
        ]
        _make_plots(resonance, aei_data, phases)


def make_plots_from_db(start: int, stop: int):
    """Calculate resonances and plot the png files for given object.

    :param int start:
    :param int stop:
    :raises ExtractError: if some problems has been appeared related to
    archive.
    """

    conn = engine.connect()
    for resonance, aei_data in find_resonances(start, stop):
        result = conn.execute('SELECT value FROM %s WHERE resonance_id=%i' %
                              (TABLENAME, resonance.id))
        phases = [x['value'] for x in result]
        _make_plots(resonance, aei_data, phases)


def _make_plots(for_resonance: ThreeBodyResonance, by_aei_data: List[str],
                with_phases: List[float]):
    apocentric_phases = [cutoff_angle(x + pi) for x in with_phases]
    try:
        if with_phases:
            _make_plot(for_resonance, by_aei_data, with_phases, False)
        if apocentric_phases:
            _make_plot(for_resonance, by_aei_data, apocentric_phases, True)
    except PhaseCountException as e:
        logging.error('%s, resonance_id = %i', str(e), for_resonance.id)


def _make_plot(for_resonance: ThreeBodyResonance, by_aei_data: List[str],
               with_phases: List[float], is_for_apocentric: bool):
    firstbody_elements, secondbody_elements = build_bigbody_elements(
        opjoin(MERCURY_DIR, '%s.aei' % BODY1),
        opjoin(MERCURY_DIR, '%s.aei' % BODY2))

    res_filepath = opjoin(OUTPUT_RES_PATH, 'A%i.res' % for_resonance.asteroid_number)

    orbital_elem_set = ComputedOrbitalElementSetFacade(
        firstbody_elements, secondbody_elements, with_phases)
    orbital_elem_set.write_to_resfile(res_filepath, by_aei_data)

    gnufile_path = _create_gnuplot_file(for_resonance.asteroid_number)
    if not os.path.exists(OUTPUT_IMAGES):
        os.makedirs(OUTPUT_IMAGES)

    out_path = opjoin(OUTPUT_IMAGES, 'A%i-res%i%s.png' % (
        for_resonance.asteroid_number, for_resonance.id,
        '-apocentric' if is_for_apocentric else ''
    ))
    with open(out_path, 'wb') as image_file:
        subprocess.call(['gnuplot', gnufile_path], stdout=image_file)


def _create_gnuplot_file(body_number):
    with open(os.path.join(PROJECT_DIR, 'view', 'multi.gnu')) as gnuplot_sample_file:
        content = gnuplot_sample_file.read()

    content = (
        content.replace('result', '%s/A%i.res' % (OUTPUT_RES_PATH, body_number))
        .replace('set xrange [0:100000]', 'set xrange [0:%i]' % CONFIG['gnuplot']['x_stop'])
        .replace('with points', 'with %s' % CONFIG['gnuplot']['type'])
    )

    if not os.path.exists(OUTPUT_GNU_PATH):
        os.makedirs(OUTPUT_GNU_PATH)

    path = opjoin(OUTPUT_GNU_PATH, 'A%i.gnu' % body_number)
    with open(path, 'w+') as gnuplot_file:
        gnuplot_file.write(content)
    return path
