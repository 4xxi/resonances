import logging
from typing import List, Tuple, Iterable
from typing import Generator

from resonances.entities import build_resonance, BodyNumberEnum
from resonances.entities import get_resonance_factory
from resonances.settings import Config
from os.path import join as opjoin

CONFIG = Config.get_params()
PROJECT_DIR = Config.get_project_dir()
SKIP_LINES = CONFIG['catalog']['astdys']['skip']
AXIS_COLUMNS = {BodyNumberEnum.two: 4, BodyNumberEnum.three: 6}
ASTDYS = opjoin(PROJECT_DIR, CONFIG['catalog']['file'])


def read_header(from_catalog: str) -> Iterable[str]:
    with open(from_catalog) as fd:
        for i, line in enumerate(fd):
            if i >= SKIP_LINES:
                break
            yield line[:-1]


def find_by_number(number: int, catalog_path: str = ASTDYS) -> List[float]:
    """Find asteroid parameters by number in catalog.

    :param int number: num for search.
    :return: list contains parameters of asteroid.
    """

    try:
        with open(catalog_path, 'r') as fd:
            for i, line in enumerate(fd):
                if i < number - 1 + SKIP_LINES:
                    continue

                arr = line.split()[1:]
                arr = [float(x) for x in arr]
                arr[4], arr[5] = arr[5], arr[4]
                return arr
    except FileNotFoundError:
        link = 'http://hamilton.dm.unipi.it/~astdys2/catalogs/allnum.cat'
        logging.error('File from astdys doesn\'t exist try this %s' % link)
        exit(-1)


class ApostropheException(Exception):
    pass


class SpaceException(Exception):
    pass


AsteroidData = Tuple[str, List[float]]


def _gen_data(from_catalog: str) -> Iterable[str]:
    with open(from_catalog, 'r') as fd:
        for i, line in enumerate(fd):
            if i < SKIP_LINES:
                continue
            yield line


def asteroid_names_gen(from_catalog: str) -> Iterable[str]:
    for line in _gen_data(from_catalog):
        name, _ = _parse_asteroid_name(line)
        yield name


def _parse_asteroid_name(line: str) -> Tuple[str, int]:
    pos = line.find("'", 1)
    if pos == -1:
        raise ApostropheException('no apostrophe in %s' % line)
    asteroid_name = line[1:pos]
    if ' ' in asteroid_name:
        raise SpaceException('Asteroid\'s name contains spaces %s' % asteroid_name)
    return asteroid_name, pos


def _parse_asteroid_data(line: str) -> AsteroidData:
    asteroid_name, pos = _parse_asteroid_name(line)
    arr = line[pos:-1].split()[1:]
    arr = [float(x) for x in arr]
    arr[4], arr[5] = arr[5], arr[4]
    return asteroid_name, arr


def asteroid_gen(catalog_path: str = ASTDYS, start: int = None, stop: int = None)\
        -> Iterable[AsteroidData]:
    with open(catalog_path, 'r') as fd:
        for i, line in enumerate(fd):
            diff = i - SKIP_LINES + 1
            if i < SKIP_LINES or start is not None and diff < start:
                continue

            if stop is not None and diff >= stop:
                break

            asteroid_data = _parse_asteroid_data(line)
            yield asteroid_data


def asteroid_list_gen(buffer_size: int, catalog_path: str = ASTDYS, start: int = None,
                      stop: int = None) -> Generator[List[AsteroidData], None, None]:
    id_buffer = []
    for i, asteroid_data in enumerate(asteroid_gen(catalog_path, start, stop)):
        diff = i + 1
        id_buffer.append(asteroid_data)

        if diff % buffer_size == 0:
            yield id_buffer
            id_buffer.clear()

    if id_buffer:
        yield id_buffer


class PossibleResonanceBuilder:
    def __init__(self, planets: Tuple[str], axis_swing: float = 0.01, catalog_path: str = ASTDYS):
        self.planets = planets
        self.axis_swing = axis_swing
        self.catalog_path = catalog_path

    def build(self, from_source: Iterable, asteroid: AsteroidData) -> List[int]:
        """
        Saves resonances to database, that are possible for pointed asteroid.
        Resonance is considering if it's semi major axis similar to semi major
        axis of asteroid from catalog. Them compares with some swing, which
        which pointed in settings.

        :param from_source: iterable data with resonance matrix.
        :param asteroid: asteroid's name and asteroid's data from catalog.
        :return: list of id numbers of resonances.
        """
        possible_resonances = []
        asteroid_parameters = asteroid[1]
        asteroid_axis = asteroid_parameters[1]
        for line in from_source:
            line_data = line.split()

            body_count = BodyNumberEnum(len(self.planets) + 1)
            assert (body_count == BodyNumberEnum.three and len(line_data) > 5 or
                    body_count == BodyNumberEnum.two)
            resonant_asteroid_axis = float(line_data[AXIS_COLUMNS[body_count]])
            if abs(resonant_asteroid_axis - asteroid_axis) <= self.axis_swing:
                resonance_factory = get_resonance_factory(
                    self.planets, line_data, asteroid[0])
                possible_resonances.append(build_resonance(resonance_factory))

        return possible_resonances
