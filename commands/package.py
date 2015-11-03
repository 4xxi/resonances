import logging
import os
import shutil
from os.path import join as opjoin
import glob
import tarfile

from settings import ConfigSingleton
from settings import PROJECT_DIR
from utils.shortcuts import logging_done

CONFIG = ConfigSingleton.get_singleton()
BODIES_COUNTER = CONFIG['integrator']['number_of_bodies']
EXPORT_BASE_DIR = opjoin(PROJECT_DIR, CONFIG['export']['base_dir'])
INTEGRATOR_DIR = opjoin(PROJECT_DIR, CONFIG['integrator']['dir'])
STRUCTURE = CONFIG['export']['structure']


def remove_export_directory(start: int, stop: int=None) -> bool:
    """Removes directory, that created by method package.

    :param start:
    :param stop:
    :return: flag says about succesful of operation
    """
    if not stop:
        stop = start + BODIES_COUNTER
    export_dir = opjoin(EXPORT_BASE_DIR, '%i-%i' % (start, stop))
    if os.path.exists(export_dir):
        logging.info('Clear directory %s...' % export_dir)
        shutil.rmtree(export_dir)
        logging_done()
        return True
    else:
        logging.info('Nothing to delete')
        return False


def package(start: int, stop: int, do_copy_res: bool, do_copy_aei: bool,
            do_gzip: bool) -> bool:
    """Create package (tar.gz archive) based on current mercury6 data.
    Current data will be removed.

    :param stop:
    :param start: first object number
    :param bool do_copy_res: copy res, gnu, png files or not
    :param bool do_copy_aei:
    :param do_gzip: archive with tar?
    :return:
    """
    if not start:
        logging.error('Specify please start value.')
        return False

    if not stop:
        stop = start + BODIES_COUNTER
    export_dir = opjoin(EXPORT_BASE_DIR, '%i-%i' % (start, stop))

    def _copy_integrator_files(with_mask: str, to_dist: str):
        files = glob.iglob(os.path.join(INTEGRATOR_DIR, with_mask))
        for item in files:
            if os.path.isfile(item):
                shutil.copy(item, to_dist)

    def _copy_aei_files():
        logging.info('Copy aei files...')
        _copy_integrator_files('*.aei', opjoin(export_dir, 'aei'))
        logging_done()

    def _copy_dmp_tmp_files():
        logging.info('Copy dmp and tmp files... ')
        _copy_integrator_files('*.dmp', opjoin(export_dir, 'mercury'))
        _copy_integrator_files('*.tmp', opjoin(export_dir, 'mercury'))
        logging_done()

    def _copy_out_files():
        logging.info('Copy out files...')
        _copy_integrator_files('*.out', opjoin(export_dir, 'mercury'))
        logging_done()

    def _copy_output_file(with_extension: str, with_index: int):
        path = opjoin(PROJECT_DIR, 'output', with_extension, 'A%i.%s' %
                      (with_index, with_extension))
        if os.path.exists(path):
            shutil.copy(path, opjoin(export_dir, with_extension))
        else:
            logging.warning('%s not found' % path)

    logging.info('Creating archive directories for asteroids %i—%i' %
                 (start, stop))
    logging.info('Creating main directory... ')

    if os.path.exists(export_dir):
        logging.info('Directory %s already exists' % export_dir)
        return False

    os.makedirs(export_dir)
    logging_done()

    logging.info('Creating subdirectories...')
    for export_directory in STRUCTURE:
        os.makedirs(opjoin(export_dir, export_directory))
    logging_done()

    if do_copy_aei:
        _copy_aei_files()

    _copy_dmp_tmp_files()
    _copy_out_files()

    if do_copy_res:
        logging.info('Copy res, gnu and png files...')

        for i in range(start, stop):
            _copy_output_file('res', i)
            _copy_output_file('gnu', i)
            _copy_output_file('png', i)
            logging_done()

    if do_gzip:
        logging.info('Archive files...')
        archive_name = 'integration%i-%i.tar.gz' % (start, stop)
        directory_name = '%i-%i' % (start, stop)
        with tarfile.open(opjoin(EXPORT_BASE_DIR, archive_name), 'w:gz') as tarf:
            tarf.add(opjoin(EXPORT_BASE_DIR, directory_name))
        logging_done()

    return True
