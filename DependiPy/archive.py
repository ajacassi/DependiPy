import ast
import pandas as pd
import os
import numpy as np
from tqdm import tqdm
import pkg_resources


class LibMapperTools:

    def __init__(self, lib_name, remove, replace_dict, exclusion, force_version, librerie_private=None, mode='lib'):
        self.lib_name = lib_name
        self.remove = remove
        self.replace_dict = replace_dict
        self.exclusion = exclusion
        self.force_version = force_version
        self.number_of_levels = 0
        self.librerie_private = librerie_private
        self.mode = mode

        # lista di colonne, serve per il codice
        self.saved_columns = ['file', 'req', 'path']

    def read_files(self):
        # vengono cergati tutti i file dentro la libreria
        df = pd.DataFrame()
        for (dirpath, dirnames, filenames) in os.walk(self.lib_name):
            # vengono salvato i percorsi di ogni file
            path = dirpath.replace("/", "").replace(".", "").replace("\\", ".")
            # il percorso viene rotto nelle sue componenti e messo in una lista
            levels = path.split(".")
            # se dopo aver eliminato le cartelle da escludere rimangono delle cartelle allora si prosegue con il parsing
            if not len(set(self.exclusion).intersection(levels)) > 0:
                # si inizializza il dataframe temporaneo in cui si salvano le librerie di ogni file uno ad uno
                req_temp = pd.DataFrame(columns=["level_" + str(i) for i in range(len(levels))] + self.saved_columns,
                                        index=[i for i in range(len(filenames))])
                # si popola il dataframe
                req_temp.loc[:, ["level_" + str(i) for i in range(len(levels))]] = levels
                req_temp.loc[:, 'path'] = path
                # si legge ogni file
                for i, file in enumerate(filenames):
                    # filtro per i soli script python
                    if file.split(".")[-1] == "py" and not file.startswith('test'):
                        try:
                            with open(dirpath + "/" + file, "r", encoding='utf-8') as f:
                                contents = f.read()
                            # il contenuto del file viene madato alla funzione che ne estrae le librerie
                            req = self.books_extraction(contents)
                            req_temp.loc[req_temp.index[i], 'file'] = file
                            req_temp.loc[req_temp.index[i], 'req'] = req
                        except ValueError as e:
                            print(f'{file} is impossible to read')
                # viene popolato un dataframe comune a tutti i file
                df = pd.concat([df, req_temp], ignore_index=True)
                # se un file non viene considerato perche non ha il .py con il drop viene eliminata la sua riga
                df = df.dropna(subset=['file'])

        # si ottiene il numero di livelli di profondita della classe
        number_of_levels = df.columns.difference(self.saved_columns).shape[0]
        # si riordinano le colonne
        df = df.loc[:, ["level_" + str(i) for i in range(number_of_levels)] + self.saved_columns]
        self.number_of_levels = number_of_levels
        return df

    # funzione parsa il testo del codice ed estrae i nomi delle librerie usate
    def books_extraction(self, text):
        modules = []
        # usando la libreria ast vengono trovati gli import
        for node in ast.iter_child_nodes(ast.parse(text)):
            if isinstance(node, ast.ImportFrom):
                modules.append(node.module)
            elif isinstance(node, ast.Import):
                modules.append(node.names[0].name)

        # se gli import erano divisi in un percorso viene preso solo il primo elemento del percorso
        def select_first(name):
            # se l'import era una cross reference viene tenuto tutto il percorso
            if name.split('.')[0] == self.lib_name:
                return name
            # se l'import era una libreria privata viene tenuto tutto il percorso
            elif name.split('.')[0] in self.librerie_private:
                return name
            # se no restituisce solo il primo termine
            else:
                return name.split('.')[0]

        # vengono tenute le libreri in modo unico
        librerie = list(set(list(map(select_first, modules))))
        return librerie

####################################################################################################################
####################################################################################################################
####################################################################################################################
####################################################################################################################

    # funzione che estrae dalla lista delle librerie quelle che appartengono alle cross referenze,
    # quindi quelle che hanno nel nome la parola lib_name
    def cross_reference_extraction(self, _list):
        cross_reference_list = []
        for _ele in _list:
            if _ele.split(".")[0] == self.lib_name:
                cross_reference_list.append(_ele)
        return cross_reference_list

    # funzione che fa pulizia sulle librerie nella lista che gli viene passata
    def cleaning(self, _list):
        elements = _list.copy()
        if len(_list) > 0:
            for _ele in elements:
                # vengono rimosse le librerie legate alle cross reference
                if _ele.split(".")[0] == self.lib_name:
                    _list.remove(_ele)
                # vengono rimossi i riferimenti alle librerie private
                elif _ele.split('.')[0] in self.librerie_private and self.mode == 'lib':  # la condizione e' elif perche la lib_name potrebbe essere anche una libreria privata
                    _list.remove(_ele)

                # vengono rimosse le librerie segnate come da eliminare
                if _ele in self.remove:
                    _list.remove(_ele)

                # vengono sostituite le librerie segnate come da sostituire
                if _ele in self.replace_dict:
                    if _ele in _list:
                        _list += self.replace_dict[_ele]
                        _list.remove(_ele)
            return _list
        else:
            # viene restituito NaN se un file non ha librerie
            return []

    @staticmethod
    def remove_unrequired(df):
        # i file che non hanno librerie e sono __init__ vengono eliminati dalla mappatura
        # mentre se un file non ha librerie viene cmq tenuto dentro i percorsi chiamabili
        allowed_files = []
        for i in range(df.shape[0]):
            if (df.loc[df.index[i], 'req'] is pd.NA) and df.loc[df.index[i], 'file'] == "__init__.py":
                allowed_files.append(False)
            else:
                allowed_files.append(True)

        # per riempire la casella req dei file che non hanno librerie con una lista vuota va inserita una lista con
        # un elemento e poi va rimosso quell'elemento
        for i in range(df.shape[0]):
            if df.loc[df.index[i], 'req'] is pd.NA:
                df.loc[df.index[i], 'req'] = ['waste_list']
                df.loc[df.index[i], 'req'].remove('waste_list')

        # vengono eliminate gli script marcati come da aliminare perche senza requisiti
        df = df.loc[allowed_files]
        return df

    @staticmethod
    def add_path(df):
        # viene creata una colonna con il contenuto del percorso di un file e il nome del file stesso
        df.loc[:, 'path_file'] = df.loc[:, 'path'] + "." + df['file'].str.replace('.py', '', regex=True)
        return df

    @staticmethod
    def cross_mapping(df, max_deep=7):  # max_deep rappresenta la profondita massima raggiungibile per una catena di cross reference
        def cross_mapper(_cross_files, _cross_lib_temp, _max_deep, _origin):
            # viene ridotto un contatore di sicurezza che impedisce di restare incastrati in una referenza circolare
            _max_deep = _max_deep - 1
            if _max_deep <= 0: return []
            # si cicla sulle cross referenze
            for cross_file in _cross_files:
                # vengono aggiornate le referenze se presenti
                if df.loc[df['path_file'] == cross_file, 'req'].shape[0] > 0:
                    _cross_lib_temp.update(set(df.loc[df['path_file'] == cross_file, 'req'].iloc[0]))
                # vengono aggiornate le cross referenze se presenti
                if df.loc[df['path_file'] == cross_file, 'cross'].shape[0] > 0:
                    chain_cross = df.loc[df['path_file'] == cross_file, 'cross'].iloc[0].copy()
                    # se il file di provenienza e' presente tra i file in cui entrare allora lo rimuovo
                    if _origin in chain_cross:
                        id_origin = chain_cross.index(_origin)
                        chain_cross.pop(id_origin)
                    if len(chain_cross) > 0:
                        # in caso di presenza di cross referenze viene chiamata ricorsivamente la funzione di mapping sulla
                        # nuova cross reference
                        _cross_lib_temp.update(cross_mapper(chain_cross, _cross_lib_temp, _max_deep, cross_file))
            return _cross_lib_temp

        cross_lib_tot = []
        # un file per volta vengono estratte tutti i requirements dalle cross referenze
        files = tqdm(range(df.shape[0]), position=0, leave=True, ascii=True, unit=' files')
        for i in files:
            cross_files = df.iloc[i, df.columns.get_loc('cross')]
            origin = df.iloc[i, df.columns.get_loc('path_file')]
            # viene chiamata la funzione che estrae le cross referenze
            cross_lib = cross_mapper(cross_files, set([]), max_deep, origin)
            # i risultati vengono salvati in una lista
            cross_lib_tot.append(list(cross_lib))

        # vengono eliminate le colonne che servivano solo alle cross referenze
        df = df.loc[:, df.columns.difference(['cross', 'path_file'])]

        # variabile che verifica il numero di cross referenze
        empty_check = 0
        for crosses in cross_lib_tot:
            empty_check += len(crosses)

        # alle referenze di ogni file vengono aggiunte le referenze estratte con il cross mapping e vengono eliminati i duplicati
        if empty_check > 0:
            _list_np = df.loc[:, 'req'] + np.array(cross_lib_tot, dtype=object)
            df.loc[:, 'req'] = _list_np.apply(set).apply(list)
        return df

    def level_explorer(self, df, level, max_levels, pre_cat, _res):
        """
            funzione ricorsica che mappa l'albero della libreria e verifica come ogni referenza dei file contenuti in un ramo
            debbano essere usati se si chiede tutte le referenze di un bivio piu un alto
        """

        # un controllo impedisce un loop infinito andando a fermare la mappatura quando si raggunge la profondita massima dell'albero
        if level >= max_levels: return _res
        # vengono ottenuti i nomi delle cartelle di uno specifico livello
        category1 = df.dropna(subset='level_' + str(level))['level_' + str(level)].unique()
        # si cicla su ogni cartella
        for cat1 in category1:
            # viene fatta la selezione del dataframe con i soli valori corispondenti a una cartella
            cat_df1 = df.loc[df['level_' + str(level)] == cat1, :].dropna(subset='level_' + str(level))
            # vengono estratti tutti i requisiti di tutti i file presenti in quella cartella e sotto cartelle
            selection1 = list(set(cat_df1.loc[:, 'req'].sum()))
            # viene mappata la posizione nell'albero
            level_name = pre_cat + cat1
            # se erano presenti requisiti si prosegue
            if len(selection1) > 0:
                # i requisiti trovati vengono caricati in un dataframe
                temp_pd = pd.DataFrame(columns=['path', 'req'], index=[0])
                temp_pd.loc[temp_pd.index[0], 'req'] = selection1
                temp_pd.loc[temp_pd.index[0], 'path'] = level_name
                _res = pd.concat([_res, temp_pd], ignore_index=True)
            # se sono prenenti altri livelli viene chiamata ricorsivamente la stessa funzione di mappatura
            _res = self.level_explorer(cat_df1, level=level + 1, max_levels=max_levels, pre_cat=level_name + ".",
                                       _res=_res)
        return _res

    def add_levels(self, df):
        # viene usata la funzione di mappatura dei requisti per cartelle
        res = self.level_explorer(df, 0, self.number_of_levels, "", pd.DataFrame())

        # al percorso di un file viene aggiunto anche il nome del file stesso
        df.loc[:, 'path'] = df.loc[:, 'path'] + "." + df['file'].str.replace('.py', '', regex=True)
        # tutti i requirements vengono messi in un unico dataframe
        res = pd.concat([res, df.loc[:, ['path', 'req']]], ignore_index=True).sort_values(by=['path'])
        return res

    def write_mapping(self, df, **kwargs):

        # per poter scrivere i requisiti nel posto giusto si riporta la posizione di lavoro nel punto di partenza se in modalita script
        if self.mode == 'script': os.chdir(self.lib_name)

        # vengono trovate tutte le librerie usate nel progetto
        single_requirements = set([item for sublist in df['req'].tolist() for item in sublist])

        distribusion_not_found, requirements_variable, requirements_versioned, variables_keys = self.clean_from_python_packages(single_requirements)

        print(f'list of distribution not found: {distribusion_not_found}')

        if ('docs_only' in kwargs and kwargs.get('docs_only') == False) or 'docs_only' not in kwargs:
            # viene scritto il file dei requisiti
            with open("requirements.txt", "w") as f:
                for s in requirements_versioned:
                    f.write(s + "\n")

        ###############################
        # da aggiungere la parte che costruisce la documentazione
        if os.path.exists('docs') and os.path.exists('mkdocs.yml'):
            for i in range(df.shape[0]):
                if df.loc[df.index[i], f'file'] != "__init__.py":
                    name = df.loc[df.index[i], 'path_file']
                    with open(f"docs/{name}.md", "w") as f:
                        f.write(f"::: {name}")

            with open("mkdocs.yml", "r") as f:
                contents_yml = f.readlines()

            for i in range(len(contents_yml)):
                contents_yml[i] = contents_yml[i].split('\n')[0]

            # se sono presenti i marker per riscrivere le librerie vengono usati
            api_is_here = True
            if '  - API:' in contents_yml:
                yml_start = contents_yml.index('  - API:') + 1
                yml_stop = contents_yml[yml_start:].index('') + yml_start
            elif 'nav:' in contents_yml:
                yml_start = contents_yml.index('nav:') + 1
                yml_start = contents_yml[yml_start:].index('') + yml_start
                yml_stop = contents_yml[yml_start:].index('') + yml_start + 1
                api_is_here = False
            else:
                yml_start, yml_stop = 0, 0
                print('missing the proper tag in the mkdocs.yml')
                exit()

            #######################################################################################
            docs = []
            temp_to_add = None
            for i in range(df.shape[0]):
                if df.loc[df.index[i], f'file'] != "__init__.py":
                    valid_col = df.loc[df.index[i], [f'level_{j}' for j in range(self.number_of_levels)]].notnull().sum() - 1
                    chapter = df.loc[df.index[i], f'level_{valid_col}']
                    row = f"    - {chapter}:"
                    space = "  "*(valid_col + 1)
                    is_to_add = space + row
                    if is_to_add != temp_to_add:
                        temp_to_add = is_to_add
                        docs.append(space + row)
                    name = df.loc[df.index[i], 'file'].split(".py")[0]
                    docs.append(space + f"      - {name}: {df.loc[df.index[i], 'path_file']}")

            #######################################################################################

            # venogono aggiunte le nuove librerie alla lista da scrivere sul file
            if api_is_here: del contents_yml[yml_start: yml_stop]
            if not api_is_here:
                docs.insert(0, '  - API:')
            docs.append('')
            contents_yml[yml_start:yml_start+1] = docs

            with open("mkdocs.yml", "w") as f:
                for s in contents_yml:
                    f.write(str(s) + "\n")

        ###############################
        if ('docs_only' in kwargs and kwargs.get('docs_only') == False) or 'docs_only' not in kwargs:

            if self.mode == 'script':
                list_privat_reference = ['[' for _ in range(len(self.librerie_private))]

                for ele in single_requirements:
                    if ele != 'waste':
                        for i, lib in enumerate(self.librerie_private):
                            if ele.split('.')[0] == lib:
                                list_privat_reference[i] += (ele + ',')

                for i in range(len(self.librerie_private)):
                    if len(list_privat_reference[i]) > 1:
                        print()
                        print(list_privat_reference[i][:-1]+']')
                print()

            if self.mode == 'lib':
                if not os.path.exists('setup.py'):
                    raise ValueError('missing the setup.py file mandatory for the script')

                df = self.cross_mapping(df)
                df = self.add_levels(df)

                # il nome del percorso viene trasformato sostituendo i . con _ ma viene mantenuto anche il nome originale
                df.loc[:, 'original'] = df.loc[:, 'path'].copy()
                df.loc[:, 'path'] = df.loc[:, 'path'].str.replace(".", "_", regex=False)

                with open("setup.py", "r") as f:
                    contents = f.readlines()

                for i in range(len(contents)):
                    contents[i] = contents[i].split('\n')[0]

                # controllare se ci sono gli star e end
                # se sono presenti i marker per riscrivere le librerie vengono usati
                if '# version go' in contents and '# version end' in contents:
                    vers_start = contents.index('# version go') + 1
                    vers_stop = contents.index('# version end')
                else:
                    vers_start, vers_stop = 0, 0
                    print('missing version go/end tag')
                    exit()

                # vengono eliminate le librerie dentro i marker
                del contents[vers_start: vers_stop]

                # venogono aggiunte le nuove librerie alla lista da scrivere sul file
                contents[vers_start:vers_start] = requirements_variable

                missing = False
                if '# start' in contents and '# stop' in contents:
                    start = contents.index('# start')
                    stop = contents.index('# stop')

                    packets = ['' for _ in range(df.shape[0])]
                    for i in range(df.shape[0]):
                        packets[i] += f"'{df.loc[df.index[i], 'original']}': ["

                        _, _, _, eles = self.clean_from_python_packages(df.loc[df.index[i], "req"])

                        j = 0
                        for ele in eles:
                            if ele != 'waste':
                                if j == 0:
                                    packets[i] += f'{ele}'
                                else:
                                    packets[i] += f', {ele}'
                                j += 1
                        packets[i] += '],'

                    packets = ['requires_dict = {'] + packets
                    packets = packets + ['}']

                    new_set_up = ['' for _ in range(start+len(contents)-stop+len(packets))]
                    new_set_up[:start+1] = contents[:start+1]
                    new_set_up[start+1:len(packets)+1] = packets
                    new_set_up[start+1+len(packets):] = contents[stop:]
                else:
                    print('missing version start/stop tag')
                    new_set_up = contents
                    missing = True

                if missing:
                    for i, line in enumerate(new_set_up):
                        if 'install_requires' in line:
                            new_set_up[i] = f'install_requires={str(variables_keys)},'.replace("'", "")

                with open("setup.py", "w") as f:
                    for s in new_set_up:
                        f.write(str(s) + "\n")

                print(os.getcwd()+"\\setup.py")

    def clean_from_python_packages(self, single_requirements):
        # vengono matchate le librerie del progetto con le versioni da usare
        requirements_versioned = []
        requirements_variable = []
        distribusion_not_found = []
        variables = []
        for req in single_requirements:
            pass_card = True

            # applicato un controllo se la libreira che si vuole inserire fa parte delle librerie private
            # in quel caso non deve essere messa nel requirement.txt
            for pl in self.librerie_private:
                if req.startswith(pl):
                    pass_card = False
                    break

            if pass_card:
                req_list = self.replace_dict[req] if req in self.replace_dict else [req]
                for req_i in req_list:
                    try:
                        version = pkg_resources.get_distribution(req_i).version
                        # se il pacchetto e' presente nella lista dei pacchetti di cui forzare la versione, viene usata la versione preimpostata
                        # in caso contrario viene usata la versione di sistema
                        version_str = self.force_version[req_i] if req_i in self.force_version else f'{req_i}=={version}'
                        requirements_versioned.append(version_str)
                        requirements_variable.append(f"{req_i.replace('-', '_')} = '{version_str}'")
                        variables.append(f"{req_i.replace('-', '_')}")
                    except pkg_resources.DistributionNotFound:
                        distribusion_not_found.append(req_i)
        return distribusion_not_found, requirements_variable, requirements_versioned, variables
