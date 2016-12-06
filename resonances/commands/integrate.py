from os.path import join as opjoin
from os.path import exists as opexists
from os import remove
from typing import Tuple
from resonances.settings import Config
from resonances.commands import load_resonances as _load_resonances
from resonances.datamining import PhaseStorage
from resonances.commands import calc as _calc
from resonances.commands import LibrationFinder
from resonances.catalog import PossibleResonanceBuilder
from abc import abstractmethod
from enum import Enum
from enum import unique

CONFIG = Config.get_params()
RESONANCE_TABLE_FILE = CONFIG['resonance_table']['file']
PROJECT_DIR = Config.get_project_dir()
RESONANCE_FILEPATH = opjoin(PROJECT_DIR, 'axis', RESONANCE_TABLE_FILE)
STEP = CONFIG['integrator']['number_of_bodies']


@unique
class IntegrationState(Enum):
    start = 0
    calc = 1
    load = 2
    find = 3


Interval = Tuple[int, int]


class Integration:
    def __init__(self):
        if opexists(self.state_file):
            self.open()
        else:
            self._state = IntegrationState.start

    def save(self, state: IntegrationState):
        with open(self.state_file, 'w') as fd:
            fd.write(str(state.value))
        self._state = state

    def open(self):
        with open(self.state_file, 'r') as fd:
            self._state = IntegrationState(int(fd.read(1)))

    @property
    def state_file(self) -> str:
        return opjoin('/tmp', 'integration_state.txt')

    @property
    def state(self) -> IntegrationState:
        return self._state


class ACommand(object):
    def __init__(self, integration: Integration, catalog: str):
        from resonances.catalog import asteroid_list_gen
        self._integration = integration
        self._catalog = catalog
        self._asteroid_list_gen = asteroid_list_gen(STEP, self._catalog)

    @abstractmethod
    def exec(self):
        pass


class CalcCommand(ACommand):
    def __init__(self, integration: Integration, catalog: str,
                 from_day: float, to_day: float):
        super(CalcCommand, self).__init__(integration, catalog)
        self._from_day = from_day
        self._to_day = to_day
        self._state = IntegrationState.calc

    def exec(self):
        if self._integration.state == IntegrationState.start:
            _calc(self._asteroid_list_gen, self._from_day, self._to_day, self.aei_path)
            self._integration.save(self._state)

    @property
    def aei_path(self):
        return opjoin('/tmp', 'aei')


class LoadCommand(ACommand):
    def __init__(self, integration: Integration, catalog: str,
                 planets: Tuple[str], axis_swing: float, gen: bool):
        super(LoadCommand, self).__init__(integration, catalog)
        self._builder = PossibleResonanceBuilder(planets, axis_swing, catalog)
        self._gen = gen
        self._state = IntegrationState.load

    def exec(self):
        if self._integration.state == IntegrationState.calc:
            for asteroid_buffer in self._asteroid_list_gen:
                _load_resonances(RESONANCE_FILEPATH, asteroid_buffer, self._builder, self._gen)
            self._integration.save(self._state)


class FindCommand(ACommand):
    def __init__(self, integration: Integration, catalog: str,
                 planets: Tuple[str], aei_path: str):
        super(FindCommand, self).__init__(integration, catalog)
        self._aei_path = aei_path
        self._finder = LibrationFinder(planets, False, True, False, False, PhaseStorage.file, True)
        self._state = IntegrationState.find

    def exec(self):
        if self._integration.state == IntegrationState.load:
            self._finder.find_by_file(self._aei_path)
            for i in range(self._start, self._stop, STEP):
                end = i + STEP if i + STEP < self._stop else self._stop
                self._finder.find(i, end, self._aei_path)
            self._integration.save(self._state)


def integrate(from_day: float, to_day: float, planets: Tuple[str],
              catalog: str, axis_swing: float, gen: bool = False):
    integration = Integration()
    calcCmd = CalcCommand(integration, catalog, from_day, to_day)
    commands = [
        calcCmd,
        LoadCommand(integration, catalog, planets, axis_swing, gen),
        FindCommand(integration, catalog, planets, calcCmd.aei_path),
    ]

    for cmd in commands:
        cmd.exec()

    remove(integration.state_file)
