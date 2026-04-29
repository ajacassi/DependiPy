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
    parser.add_argument('-ip', '--inline_private',
                        help="inline the Requires-Dist of pip-installed private libraries into "
                             "requirements.txt (transitive expansion). Requires the private libs "
                             "to be installed in the current environment.",
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

    # parent della libreria: e' qui che sta setup.py o pyproject.toml in mode lib
    setup_candidate = lib_root.parent / 'setup.py'
    toml_candidate = lib_root.parent / 'pyproject.toml'

    # mode lib se esiste setup.py oppure pyproject.toml (setup.py ha precedenza)
    detected_mode = 'lib' if (setup_candidate.exists() or toml_candidate.exists()) else 'script'
    mode = kwargs['mode'] if kwargs['mode'] is not None else detected_mode
    print(f'selected mode: {mode}')

    # in mode lib si scrive nel parent (dove c'e' setup.py o pyproject.toml); in mode script si lavora dentro la cartella stessa
    working_dir = lib_root.parent if mode == 'lib' else lib_root

    lmt = LibMapperTools(lib_name=lib_name, lib_root=lib_root, working_dir=working_dir,
                         remove=remove, replace_dict=replace_dict, exclusion=exclusion,
                         force_version=force_version, librerie_private=librerie_private, mode=mode)

    records = lmt.read_files()
    lmt.add_path(records)

    # estraggo le cross-reference e applico la pulizia ad ogni record
    for r in records:
        r.cross = lmt.cross_reference_extraction(r.req)
    for r in records:
        r.req = lmt.cleaning(r.req)

    lmt.write_mapping(records, **kwargs)


if __name__ == '__main__':

    main()