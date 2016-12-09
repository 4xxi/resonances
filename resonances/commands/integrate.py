"""
Module aims providing complete cycle resonance integration. The main function
of this module is method "integrate".
"""
import logging
import json
from os.path import join as opjoin
from os.path import exists as opexists
from os import remove
from os import mkdir
from resonances.datamining import ResonanceAeiData
from typing import Iterable
from shutil import rmtree
from typing import Tuple
from typing import List
from typing import Dict
from functools import reduce
from operator import add
from resonances.settings import Config
from resonances.commands import load_resonances
from resonances.datamining import PhaseStorage
from resonances.commands import calc
from resonances.commands import LibrationFinder
from resonances.catalog import PossibleResonanceBuilder
from resonances.datamining import get_resonances_with_id
from resonances.entities import ResonanceMixin
from abc import abstractmethod
from enum import Enum
from enum import unique
from resonances.catalog import asteroid_list_gen
from os import listdir

CONFIG = Config.get_params()
RESONANCE_TABLE_FILE = CONFIG['resonance_table']['file']
PROJECT_DIR = Config.get_project_dir()
RESONANCE_FILEPATH = opjoin(PROJECT_DIR, 'axis', RESONANCE_TABLE_FILE)
STEP = CONFIG['integrator']['number_of_bodies']


@unique
class _IntegrationState(Enum):
    start = 0
    calc = 1
    load = 2
    find = 3


Interval = Tuple[int, int]


class _Integration:
    """
    Class aims to store state of complete cycle of integration. It also
    contains neccessary options used by related commands.
    """
    def __init__(self, catalog: str):
        if opexists(self.state_file):
            self.open()
        else:
            self._state = _IntegrationState.start
        self.catalog = catalog
        self.files_with_aggregated_asteroids = []

    def save(self, state: _IntegrationState):
        with open(self.state_file, 'w') as fd:
            fd.write(str(state.value))
        self._state = state

    def open(self):
        with open(self.state_file, 'r') as fd:
            self._state = _IntegrationState(int(fd.read(1)))

    @property
    def agres_folder(self):
        return opjoin('/tmp', 'resonances')

    @property
    def state_file(self) -> str:
        return opjoin('/tmp', 'integration_state.txt')

    @property
    def state(self) -> _IntegrationState:
        return self._state

    @property
    def aei_path(self):
        return opjoin('/tmp', 'aei')


class _ACommand(object):
    def __init__(self, integration: _Integration):
        self._integration = integration
        self._catalog = integration.catalog
        self._asteroid_list_gen = asteroid_list_gen(STEP, self._catalog)

    @abstractmethod
    def exec(self):
        pass


class _CalcCommand(_ACommand):
    """
    Used for calling mercury6 that will predict orbital elements and saves
    results to /tmp/aei/*.aei files.
    """
    def __init__(self, integration: _Integration, from_day: float, to_day: float):
        super(_CalcCommand, self).__init__(integration)
        self._from_day = from_day
        self._to_day = to_day
        self._state = _IntegrationState.calc

    def exec(self):
        if self._integration.state == _IntegrationState.start:
            calc(self._asteroid_list_gen, self._from_day, self._to_day, self._integration.aei_path)
            self._integration.save(self._state)


class _LoadCommand(_ACommand):
    """
    Command generates resonance table, loads it to database and saves
    resonances id to /tmp/resonances/agres-<asteroid-buffer-number>.json.
    """
    def __init__(self, integration: _Integration, planets: Tuple[str], axis_swing: float, gen: bool):
        super(_LoadCommand, self).__init__(integration)
        self._builder = PossibleResonanceBuilder(planets, axis_swing, self._catalog)
        self._gen = gen
        self._state = _IntegrationState.load

    def exec(self):
        """
        Loads resonances and makes list of files contains aggregated the
        resonances' id by asteroid.
        """
        if self._integration.state == _IntegrationState.calc:
            for i, asteroid_buffer in enumerate(self._asteroid_list_gen):
                aggregated_resonances = load_resonances(
                    RESONANCE_FILEPATH, asteroid_buffer, self._builder, self._gen)
                agres_folder = self._integration.agres_folder
                if opexists(agres_folder):
                    rmtree(agres_folder)
                mkdir(agres_folder)
                filename = opjoin(agres_folder, 'agres-%i.json' % i)
                with open(filename, 'w') as fd:
                    json.dump(aggregated_resonances, fd)
                self._integration.files_with_aggregated_asteroids.append(filename)
            self._integration.save(self._state)


class _FindCommand(_ACommand):
    """
    _FindCommand produced search librations in data from _LoadCommand instance.
    It needs:
        * aei files that will be get from path pointed in _Integration instance,
        that should be produced by _CalcCommand instance.
        * resonances id number for mining the resonances from a database and search
        librations in him for asteroids represented in aei files.
    """
    def __init__(self, integration: _Integration, planets: Tuple[str], integers: List[str]):
        super(_FindCommand, self).__init__(integration)
        self._aei_path = self._integration.aei_path
        self._finder = LibrationFinder(planets, False, True, False, False, PhaseStorage.file, True)
        self._state = _IntegrationState.find
        self._planets = planets
        self._integers = integers

    def _resonace_aei_gen(self, resonances: Iterable[ResonanceMixin]) -> Iterable[ResonanceAeiData]:
        """Resolves aei data and resonance by resonance's asteroid."""
        asteroid_name = None
        aei_data = None
        for resonance in resonances:
            print(resonance.id)
            if asteroid_name != resonance.small_body.name:
                asteroid_name = resonance.small_body.name
                with open(opjoin(self._aei_path, '%s.aei' % asteroid_name)) as fd:
                    aei_data = [x for x in fd]
            assert aei_data
            yield resonance, aei_data

    def exec(self):
        """
        Method does next:
            1) Check /tmp/resonances/agres-*.json files and set them to
            Integration instance if it is neccessary.
            2) Stops the application if files not found.
            3) Gets resonances from database and filter them by integer expression.
            4) Links to mined resonances' asteroid predicted orbital elements from aei data. 
            5) Finds librations in resonances.
        """
        if not self._integration.files_with_aggregated_asteroids:
            agres_folder = self._integration.agres_folder
            self._integration.files_with_aggregated_asteroids =\
                [opjoin(agres_folder, x) for x in listdir(agres_folder)]

        if not self._integration.files_with_aggregated_asteroids:
            logging.error('We have no resonances')
            exit(-1)

        if self._integration.state == _IntegrationState.load:
            for filename in self._integration.files_with_aggregated_asteroids:
                with open(filename) as fd:
                    aggregated_resonances_id = json.load(fd)  # type: Dict[str, List[int]]
                    resonaces_id = reduce(add, aggregated_resonances_id.values())
                    resonance_gen = get_resonances_with_id(
                        resonaces_id, self._planets, self._integers)
                    gen = self._resonace_aei_gen(resonance_gen)

                    self._finder.find_by_resonances(gen, (self._aei_path,))
            self._integration.save(self._state)


def integrate(from_day: float, to_day: float, planets: Tuple[str], catalog: str,
              axis_swing: float, gen: bool, integers: List[str]):
    """
    Make complete cycle from calculation aei files to search librations. State
    of the cycle is saved after every step to file /tmp/integration_state.txt.
    If integration will be crashed by some reasons then state of it will be
    repaired from this file and considered in every command.

    The process contains 3 steps:
        1) Prediction orbital elements by Mercury6 and saving results to /tmp/aei/*.aei.
        2) Generating resonance table and loading from it suitable resonances for asteroids.
        3) Search librations in loaded resonances.
    """
    integration = _Integration(catalog)
    cmds = [
        _CalcCommand(integration, from_day, to_day),
        _LoadCommand(integration, planets, axis_swing, gen),
        _FindCommand(integration, planets, integers)
    ]

    for cmd in cmds:
        cmd.exec()

    remove(integration.state_file)

