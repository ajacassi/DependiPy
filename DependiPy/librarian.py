import os
import argparse
from DependiPy.archive import LibMapperTools
import json


def main():

    parser = argparse.ArgumentParser(prog='library-mapper', description="Map the requirements of a project")
    parser.add_argument('-p', '--path',
                        help="folder/file path, if mode lib it needs the path to the folder deeper than setup.py",
                        required=True)
    parser.add_argument('-m', '--mode', help="lib parser or script parser (lib,script)", required=False)
    parser.add_argument('-c', '--config', help="config file", required=False, default='config.json')
    parser.add_argument('-do', '--docs_only', help="generate only the documentation", required=False, default=False)

    kwargs = vars(parser.parse_args())

    try:
        with open(kwargs['config']) as json_file:
            config = json.load(json_file)
    except:
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

    # percorso della libreria
    path = kwargs['path']
    os.chdir(path)

    # nome della cartella che contiene la libreria, rappresenta il livello 0
    lib_name = os.path.normpath(os.getcwd()).split('\\')
    if lib_name[-1] == '':
        lib_name = lib_name[-2]
    else:
        lib_name = lib_name[-1]

    # esco dalla cartella selezionata per vederla da fuori
    os.chdir('..')

    # se trovo il file setup.py e non ho un mode dagli argomenti passati allora imposto mode come lib
    mode = 'lib' if os.path.exists('setup.py') else 'script'
    mode = kwargs['mode'] if kwargs['mode'] is not None else mode
    print(f'selected mode: {mode}')

    lmt = LibMapperTools(lib_name=lib_name, remove=remove, replace_dict=replace_dict, exclusion=exclusion,
                         force_version=force_version, librerie_private=librerie_private, mode=mode)

    requirements_pd = lmt.read_files()

    requirements_pd = lmt.add_path(requirements_pd)

    # applico la funzione che estrae le cross reference e la applico alla colonna delle librerie
    requirements_pd.loc[:, 'cross'] = requirements_pd.loc[:, 'req'].apply(lmt.cross_reference_extraction)

    requirements_pd.loc[:, 'req'] = requirements_pd.loc[:, 'req'].apply(lmt.cleaning)

    lmt.write_mapping(requirements_pd, **kwargs)


if __name__ == '__main__':

    main()