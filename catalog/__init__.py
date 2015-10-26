from settings import ConfigSingleton


class AstDys:
    @staticmethod
    def find_by_number(number: int) -> list[float]:
        """Find asteroid parameters by number.

        :param num int: num for search.
        :return list: array contains parameters of asteroid.
        """
        CONFIG = ConfigSingleton.get_singleton()
        SKIP_LINES = CONFIG['catalog']['astdys']['skip']
        PATH = CONFIG['catalog']['file']

        with open(PATH, 'r') as f_file:
            for i, line in enumerate(f_file):
                if i < number + SKIP_LINES:
                    continue

                arr = line.split(' ')[1:]
                arr = [float(x) for x in arr]
                arr[4], arr[5] = arr[5], arr[4]
                return arr