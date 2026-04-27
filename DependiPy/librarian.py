import argparse
import json
from pathlib import Path

from DependiPy.archive import LibMapperTools


def main():

    parser = argparse.ArgumentParser(prog='library-mapper', description="Map the requirements of a project")
    parser.add_argument('-p', '--path',
                        help="folder/file path, if mode lib it needs the path to the folder deeper than setup.py",
                        required=True)
    parser.add_argument('-m', '--mode', help="lib parser or script parser (lib,script)", required=False)
    parser.add_argument('-c', '--config', help="config file", required=False, default='config.json')
    parser.add_argument('-do', '--docs_only', help="generate only the documentation",
                        action='store_true')

    kwargs = vars(parser.parse_args())

    try:
        with open(kwargs['config'], encoding='utf-8') as json_file:
            config = json.load(json_file)
    except (FileNotFoundError, json.JSONDecodeError):
        config = {}

    librerie_private = config.get('private_lib', [])
    print("privat libraries: ", librerie_private)
    # nome delle cartelle da non considerare per la mappatura
    exclusion = config.get('exclude_folder', [])
    # lista di librerie aggiuntive che non si vuole inseire nei requirements se fossero presenti
    remove = config.get('exclude_lib', [])
    # dizionario per sostituire alcuni nomi se serve
    replace_dict = config.get('replace_lib', {})
    # se nel config non erano state inseriti i rimpiazzi dentro una lista qui vengono gestiti in modo da essere nel formato atteso
    if len(replace_dict) > 0:
        for name in replace_dict:
            if isinstance(replace_dict[name], str):
                replace_dict[name] = [replace_dict[name]]

    # lista di librerie di cui si vuole forzare la versione
    force_version = config.get('force_version', {})

    # path della libreria, risolto in assoluto: cosi non dipendiamo dalla cwd e funziona su Linux/Mac/Windows
    lib_root = Path(kwargs['path']).resolve()
    if not lib_root.is_dir():
        raise NotADirectoryError(f"path '{lib_root}' is not a directory")
    lib_name = lib_root.name

    # parent della libreria: e' qui che sta setup.py in mode lib, ed e' qui che si scrive
    # requirements.txt / si aggiorna setup.py
    setup_candidate = lib_root.parent / 'setup.py'

    # se trovo il file setup.py e non ho un mode dagli argomenti passati allora imposto mode come lib
    detected_mode = 'lib' if setup_candidate.exists() else 'script'
    mode = kwargs['mode'] if kwargs['mode'] is not None else detected_mode
    print(f'selected mode: {mode}')

    # in mode lib si scrive nel parent (dove c'e' setup.py); in mode script si lavora dentro la cartella stessa
    working_dir = lib_root.parent if mode == 'lib' else lib_root

    lmt = LibMapperTools(lib_name=lib_name, lib_root=lib_root, working_dir=working_dir,
                         remove=remove, replace_dict=replace_dict, exclusion=exclusion,
                         force_version=force_version, librerie_private=librerie_private, mode=mode)

    requirements_pd = lmt.read_files()

    requirements_pd = lmt.add_path(requirements_pd)

    # applico la funzione che estrae le cross reference e la applico alla colonna delle librerie
    requirements_pd.loc[:, 'cross'] = requirements_pd.loc[:, 'req'].apply(lmt.cross_reference_extraction)

    requirements_pd.loc[:, 'req'] = requirements_pd.loc[:, 'req'].apply(lmt.cleaning)

    lmt.write_mapping(requirements_pd, **kwargs)


if __name__ == '__main__':

    main()