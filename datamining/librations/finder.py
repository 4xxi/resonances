import math
import json
from typing import List

from entities import Phase
from entities.dbutills import REDIS
from utils.shortcuts import cutoff_angle


class CirculationYearsFinder:
    def __init__(self, resonance_id: int, is_for_apocentric: bool):
        self._is_for_apocentric = is_for_apocentric
        self._resonance_id = resonance_id

    def get_years(self) -> List[float]:
        """Find circulations in file.
        """
        result_breaks = []  # circulation breaks by OX
        p_break = 0
        previous_resonant_phase = None
        prev_year = None

        phases = REDIS.lrange('%s:%i' % (Phase.__tablename__, self._resonance_id), 0, -1)
        if not phases:
            raise NoPhaseException('no resonant phases for resonance_id: %i' %
                                   self._resonance_id)

        for phase in phases:  # type: bytes
            phase = json.loads(phase.decode('utf-8').replace('\'', '"'))  # Dict[str, float]
            # If the distance (OY axis) between new point and previous morf
            # than PI then there is a break (circulation)
            if self._is_for_apocentric:
                resonant_phase = cutoff_angle(phase['value'] + math.pi)
            else:
                resonant_phase = phase['value']
            if resonant_phase:
                if (previous_resonant_phase and
                        (abs(previous_resonant_phase - resonant_phase) >= math.pi)):
                    c_break = 1 if (previous_resonant_phase - resonant_phase) > 0 else -1

                    # For apocentric libration there could be some breaks by
                    # following schema: break on 2*Pi, then break on 2*Pi e.t.c
                    # So if the breaks are on the same value there is no
                    # circulation at this moment
                    if (c_break != p_break) and (p_break != 0):
                        del result_breaks[len(result_breaks) - 1]

                    assert prev_year is not None
                    result_breaks.append(prev_year)
                    p_break = c_break

            previous_resonant_phase = resonant_phase
            prev_year = phase['year']

        return result_breaks


class NoPhaseException(Exception):
    pass