import ast
import os
import sys
import warnings
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from tqdm import tqdm


@dataclass
class FileRecord:
    """Rappresenta un singolo file Python mappato dentro la libreria/script."""
    levels: list   # parts del path relativo, es. ['mylib', 'sub']
    file: str      # nome del file con estensione, es. 'foo.py'
    req: list      # lista dei requirements estratti (e poi puliti)
    path: str      # path con notazione a punti, es. 'mylib.sub'
    cross: list = field(default_factory=list)  # cross-reference interne (popolato dopo)
    path_file: str = ""                         # path completo del modulo, es. 'mylib.sub.foo'


class LibMapperTools:

    def __init__(self, lib_name, lib_root, working_dir, remove, replace_dict, exclusion, force_version,
                 librerie_private=None, mode='lib'):
        self.lib_name = lib_name
        self.lib_root = Path(lib_root).resolve()
        self.working_dir = Path(working_dir).resolve()
        self.remove = remove
        self.replace_dict = replace_dict
        self.exclusion = exclusion
        self.force_version = force_version
        self.number_of_levels = 0
        self.librerie_private = librerie_private if librerie_private is not None else []
        self.mode = mode

        # nomi dei moduli locali al progetto (file .py e cartelle dentro lib_root). In mode script
        # gli script "fratelli" si importano direttamente per nome (es. `from utils import x`):
        # senza questo set verrebbero scambiati per dipendenze esterne mancanti. Popolato in read_files.
        self.local_modules = set()

    def read_files(self):
        """Esplora self.lib_root e produce una lista di FileRecord, uno per ogni .py valido."""
        records = []
        # base da cui calcolare i percorsi relativi: il parent della cartella della libreria,
        # cosi che il modulo di primo livello sia self.lib_name
        base = self.lib_root.parent
        local_modules = set()
        max_levels = 0
        for (dirpath, dirnames, filenames) in os.walk(self.lib_root):
            # path relativo alla base, normalizzato in forma "lib.sub.folder" (cross-platform)
            rel_parts = Path(dirpath).resolve().relative_to(base).parts
            path = ".".join(rel_parts)
            levels = list(rel_parts)
            # se il path include una cartella esclusa, salto interamente questo dirpath
            if set(self.exclusion).intersection(levels):
                continue
            # raccolgo i nomi dei moduli locali: cartelle (potenziali sub-package) e file .py
            # senza estensione. Servono in mode script per non confondere import "fratelli" con
            # dipendenze esterne mancanti.
            for d in dirnames:
                if d not in self.exclusion and not d.startswith('__'):
                    local_modules.add(d)
            for f in filenames:
                if f.endswith('.py') and f != '__init__.py':
                    local_modules.add(f[:-3])

            for file in filenames:
                # filtro per i soli script python
                if not (file.endswith('.py') and not file.startswith('test')):
                    continue
                full_path = os.path.join(dirpath, file)
                try:
                    with open(full_path, "r", encoding='utf-8') as f:
                        contents = f.read()
                except (OSError, UnicodeDecodeError) as e:
                    print(f'{file} is impossible to read ({type(e).__name__}: {e})')
                    continue
                try:
                    req = self.books_extraction(contents)
                except SyntaxError as e:
                    print(f'{file} has a syntax error and will be skipped ({e})')
                    continue
                records.append(FileRecord(levels=levels, file=file, req=req, path=path))

            if len(levels) > max_levels:
                max_levels = len(levels)

        self.number_of_levels = max_levels
        self.local_modules = local_modules
        return records

    # funzione parsa il testo del codice ed estrae i nomi delle librerie usate
    def books_extraction(self, text):
        modules = []
        # ast.walk esplora tutto l'albero, non solo il livello top: cosi vengono catturati anche gli import
        # dentro try/except, funzioni, classi, blocchi if (es. lazy imports)
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.ImportFrom):
                # i relative imports (from . import x, from .sub import y) sono interni al package
                # e non vanno tracciati come dipendenze esterne
                if node.level == 0 and node.module:
                    modules.append(node.module)
            elif isinstance(node, ast.Import):
                # 'import a, b, c' produce piu alias: vanno raccolti tutti
                for alias in node.names:
                    modules.append(alias.name)

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
        # costruisco una lista nuova invece di mutare quella in input: cosi le condizioni non si
        # interferiscono fra loro (un elemento da rimuovere e da sostituire non finisce piu in
        # double-remove con ValueError)
        cleaned = []
        for _ele in _list:
            head = _ele.split('.')[0]
            # cross-reference interne alla libreria: vengono gestite altrove (cross_mapping)
            if head == self.lib_name:
                continue
            # librerie private in mode lib: non finiscono nei requirements (non sono su PyPI)
            if head in self.librerie_private and self.mode == 'lib':
                continue
            # in mode script: i moduli "fratelli" dello stesso progetto (file .py / cartelle sotto
            # lib_root) si importano per nome diretto e non sono dipendenze esterne
            if self.mode == 'script' and head in self.local_modules:
                continue
            # librerie esplicitamente da escludere
            if _ele in self.remove:
                continue
            # librerie da sostituire (es. sklearn -> scikit-learn)
            if _ele in self.replace_dict:
                cleaned.extend(self.replace_dict[_ele])
                continue
            cleaned.append(_ele)

        # dedup mantenendo l'ordine di prima apparizione
        seen = set()
        result = []
        for el in cleaned:
            if el not in seen:
                seen.add(el)
                result.append(el)
        return result

    @staticmethod
    def add_path(records):
        """Riempie il campo path_file di ogni record (es. 'mylib.sub.foo')."""
        for r in records:
            stem = r.file[:-3] if r.file.endswith('.py') else r.file
            r.path_file = f"{r.path}.{stem}"
        return records

    @staticmethod
    def cross_mapping(records, max_deep=7):
        """Per ogni record, raccoglie ricorsivamente i requirements provenienti dalle cross-reference
        interne. max_deep limita la profondita per evitare loop su riferimenti circolari."""
        # indice path_file -> record per lookup O(1) (prima erano scan lineari del df)
        by_path = {r.path_file: r for r in records}

        def cross_mapper(cross_files, accumulated, depth, origin):
            depth = depth - 1
            if depth <= 0:
                return accumulated
            for cross_file in cross_files:
                target = by_path.get(cross_file)
                if target is None:
                    continue
                accumulated.update(target.req)
                chain_cross = list(target.cross)
                # rimuovo il file di provenienza per evitare il rimbalzo immediato
                if origin in chain_cross:
                    chain_cross.remove(origin)
                if chain_cross:
                    cross_mapper(chain_cross, accumulated, depth, cross_file)
            return accumulated

        for r in tqdm(records, position=0, leave=True, ascii=True, unit=' files'):
            cross_lib = cross_mapper(r.cross, set(), max_deep, r.path_file)
            if cross_lib:
                # union + dedup mantenendo un ordine deterministico (alfabetico)
                r.req = sorted(set(r.req) | cross_lib)
        return records

    def level_explorer(self, records, level, max_levels, pre_cat, results):
        """Esplora ricorsivamente l'albero delle cartelle: per ogni "bivio" raccoglie l'unione dei
        requirements di tutti i file sotto quel sottoalbero. Cosi un install
        `pip install ./lib[mylib.sub]` puo tirare giu tutte le dipendenze del sotto-package.
        """
        if level >= max_levels:
            return results
        # group by levels[level]: solo i record che arrivano almeno fino a questo livello
        groups = {}
        for r in records:
            if len(r.levels) > level:
                groups.setdefault(r.levels[level], []).append(r)

        for cat, group in groups.items():
            # unione dei requirements di tutti i file del sottoalbero
            all_req = set()
            for r in group:
                all_req.update(r.req)
            level_name = pre_cat + cat
            if all_req:
                results.append({'path': level_name, 'req': sorted(all_req)})
            self.level_explorer(group, level + 1, max_levels, level_name + ".", results)
        return results

    def add_levels(self, records):
        # mappa i requirements a livello di cartella
        results = self.level_explorer(records, 0, self.number_of_levels, "", [])
        # aggiunge i path completi dei file (path + filename senza .py)
        for r in records:
            stem = r.file[:-3] if r.file.endswith('.py') else r.file
            results.append({'path': f"{r.path}.{stem}", 'req': r.req})
        results.sort(key=lambda x: x['path'])
        return results

    def write_mapping(self, records, **kwargs):

        # working_dir = parent della libreria (mode lib, dove c'e' setup.py) o la libreria stessa (mode script).
        # Tutte le scritture passano per questo path: niente piu os.chdir.
        wd = self.working_dir

        # vengono trovate tutte le librerie usate nel progetto
        single_requirements = set()
        for r in records:
            single_requirements.update(r.req)

        distribution_not_found, requirements_variable, requirements_versioned, variables_keys = self.clean_from_python_packages(single_requirements)

        print(f'list of distribution not found: {distribution_not_found}')

        if not kwargs.get('docs_only', False):
            # viene scritto il file dei requisiti
            with open(wd / "requirements.txt", "w", encoding='utf-8') as f:
                for s in requirements_versioned:
                    f.write(s + "\n")

        ###############################
        # da aggiungere la parte che costruisce la documentazione
        docs_dir = wd / 'docs'
        mkdocs_yml = wd / 'mkdocs.yml'
        if docs_dir.exists() and mkdocs_yml.exists():
            for r in records:
                if r.file != "__init__.py":
                    with open(docs_dir / f"{r.path_file}.md", "w", encoding='utf-8') as f:
                        f.write(f"::: {r.path_file}")

            with open(mkdocs_yml, "r", encoding='utf-8') as f:
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
                raise ValueError(
                    f"missing the proper tag in {mkdocs_yml}: expected '  - API:' or 'nav:'"
                )

            #######################################################################################
            docs = []
            temp_to_add = None
            for r in records:
                if r.file != "__init__.py":
                    # indice della cartella che contiene il file: e' l'ultimo livello in r.levels
                    valid_col = len(r.levels) - 1
                    chapter = r.levels[valid_col]
                    row = f"    - {chapter}:"
                    space = "  " * (valid_col + 1)
                    is_to_add = space + row
                    if is_to_add != temp_to_add:
                        temp_to_add = is_to_add
                        docs.append(space + row)
                    name = r.file.split(".py")[0]
                    docs.append(space + f"      - {name}: {r.path_file}")

            #######################################################################################

            # venogono aggiunte le nuove librerie alla lista da scrivere sul file
            if api_is_here: del contents_yml[yml_start: yml_stop]
            if not api_is_here:
                docs.insert(0, '  - API:')
            docs.append('')
            contents_yml[yml_start:yml_start+1] = docs

            with open(mkdocs_yml, "w", encoding='utf-8') as f:
                for s in contents_yml:
                    f.write(str(s) + "\n")

        ###############################
        if not kwargs.get('docs_only', False):

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
                setup_path = wd / 'setup.py'
                if not setup_path.exists():
                    raise ValueError(f'missing setup.py at {setup_path}, mandatory for mode lib')

                records = self.cross_mapping(records)
                # entries: list[dict] con keys 'path', 'req' (uno per cartella + uno per file)
                entries = self.add_levels(records)

                # il nome del percorso viene tenuto come 'original' (con i punti) e usato come chiave
                # del requires_dict in setup.py
                for e in entries:
                    e['original'] = e['path']

                with open(setup_path, "r", encoding='utf-8') as f:
                    contents = f.readlines()

                for i in range(len(contents)):
                    contents[i] = contents[i].split('\n')[0]

                # controllare se ci sono gli star e end
                # se sono presenti i marker per riscrivere le librerie vengono usati
                if '# version go' in contents and '# version end' in contents:
                    vers_start = contents.index('# version go') + 1
                    vers_stop = contents.index('# version end')
                else:
                    raise ValueError(
                        f"missing '# version go' / '# version end' markers in {setup_path}"
                    )

                # vengono eliminate le librerie dentro i marker
                del contents[vers_start: vers_stop]

                # venogono aggiunte le nuove librerie alla lista da scrivere sul file
                contents[vers_start:vers_start] = requirements_variable

                missing = False
                if '# start' in contents and '# stop' in contents:
                    start = contents.index('# start')
                    stop = contents.index('# stop')

                    packets = []
                    for e in entries:
                        line = f"'{e['original']}': ["

                        _, _, _, eles = self.clean_from_python_packages(e['req'])

                        non_waste = [el for el in eles if el != 'waste']
                        line += ', '.join(non_waste)
                        line += '],'
                        packets.append(line)

                    packets = ['requires_dict = {'] + packets + ['}']

                    new_set_up = list(contents[:start + 1])
                    new_set_up += packets
                    new_set_up += contents[stop:]
                else:
                    print('missing version start/stop tag')
                    new_set_up = contents
                    missing = True

                if missing:
                    for i, line in enumerate(new_set_up):
                        if 'install_requires' in line:
                            new_set_up[i] = f'install_requires={str(variables_keys)},'.replace("'", "")

                with open(setup_path, "w", encoding='utf-8') as f:
                    for s in new_set_up:
                        f.write(str(s) + "\n")

                print(str(setup_path))

    def clean_from_python_packages(self, single_requirements):
        # nomi dei moduli della stdlib: filtrati senza warning perche non vanno nei requirements.
        # sys.stdlib_module_names esiste da Python 3.10; sotto, fallback a frozenset vuoto.
        stdlib_names = getattr(sys, 'stdlib_module_names', frozenset())

        requirements_versioned = []
        requirements_variable = []
        distribution_not_found = []
        variables = []
        for req in single_requirements:
            # salto le librerie private (non sono su PyPI)
            if any(req.startswith(pl) for pl in self.librerie_private):
                continue

            req_list = self.replace_dict[req] if req in self.replace_dict else [req]
            for req_i in req_list:
                # i moduli della stdlib non vanno nei requirements e non sono un errore
                if req_i in stdlib_names:
                    continue
                try:
                    version = metadata.version(req_i)
                    # se il pacchetto e' presente nella lista dei pacchetti di cui forzare la versione, viene usata la versione preimpostata
                    # in caso contrario viene usata la versione di sistema
                    version_str = self.force_version[req_i] if req_i in self.force_version else f'{req_i}=={version}'
                    requirements_versioned.append(version_str)
                    requirements_variable.append(f"{req_i.replace('-', '_')} = '{version_str}'")
                    variables.append(f"{req_i.replace('-', '_')}")
                except metadata.PackageNotFoundError:
                    # libreria importata ma non installata e non stdlib: prima veniva esclusa silenziosamente
                    # (=> requirements.txt incompleti senza segnale). Ora warning visibile.
                    distribution_not_found.append(req_i)
                    warnings.warn(
                        f"Package '{req_i}' is imported but not installed in the current "
                        f"environment and is not part of the standard library. It will NOT "
                        f"be added to requirements.txt. Install it, or add it to "
                        f"'private_lib' / 'exclude_lib' / 'replace_lib' in the config.",
                        stacklevel=2,
                    )
        return distribution_not_found, requirements_variable, requirements_versioned, variables
