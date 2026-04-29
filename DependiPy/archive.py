import ast
import os
import re
import sys
import warnings
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from tqdm import tqdm
import tomlkit


# match del nome di un pacchetto all'inizio di una stringa Requires-Dist.
# I nomi PyPI ammettono lettere, numeri, '-', '_', '.' (PEP 508). La regex ferma al primo char
# non valido (spazio, parentesi, comparatore, semicolon, ecc.).
_PKG_NAME_RE = re.compile(r'^\s*([A-Za-z0-9_][A-Za-z0-9_.\-]*)')


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

        # nomi delle librerie private effettivamente importate dal codice analizzato. Popolato in
        # cleaning(). Serve a write_mapping quando inline_private=True per espandere le Requires-Dist
        # delle sole librerie private davvero usate (e non di tutte quelle in config).
        self.used_private_libs = set()

        # path completi degli import di librerie private (es. 'Tages.preprocess.time_series.data_preparation').
        # Serve in mode script con --inline_private a selezionare gli extras della lib privata da
        # espandere: una libreria privata mappata con DependiPy ha le sue dipendenze in extras_require,
        # uno per ramo, e qui si tiene traccia di quali rami sono effettivamente importati.
        self.used_private_paths = set()

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
            # tengo traccia delle librerie private effettivamente importate: e' l'input per
            # l'espansione delle Requires-Dist quando inline_private=True
            if head in self.librerie_private:
                self.used_private_libs.add(head)
                # in mode script gli import privati sono conservati col path completo
                # (es. 'Tages.preprocess.time_series.data_preparation'): lo salvo per
                # poter selezionare gli extras corrispondenti a inline-private time
                if self.mode == 'script':
                    self.used_private_paths.add(_ele)
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

        # se richiesto, espando le Requires-Dist delle librerie private effettivamente importate
        # nel codice. In questo modo le dipendenze transitive di una lib privata diventano
        # dipendenze dirette del progetto, evitando che chi installa il progetto debba avere
        # accesso alla lib privata per scoprirne i requirements.
        if kwargs.get('inline_private', False) and self.used_private_libs:
            extra = self._expand_private_lib_dependencies(
                self.used_private_libs, self.used_private_paths,
            )
            if extra:
                print(f"inline-private: adding {len(extra)} transitive deps from "
                      f"{sorted(self.used_private_libs)} "
                      f"(branches: {sorted(self.used_private_paths) or 'base only'}): "
                      f"{sorted(extra)}")
                single_requirements.update(extra)

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
                toml_path = wd / 'pyproject.toml'

                if setup_path.exists():
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

                else:
                    # pyproject.toml (esistente o da generare)
                    if not toml_path.exists():
                        self._generate_pyproject_toml(toml_path)
                    records = self.cross_mapping(records)
                    entries = self.add_levels(records)
                    self._write_toml_mapping(toml_path, entries, requirements_versioned)
                    print(str(toml_path))

    def _detect_version(self):
        """Cerca version.py dentro lib_root e restituisce la stringa di versione trovata."""
        version_file = self.lib_root / 'version.py'
        if version_file.exists():
            try:
                with open(version_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        m = re.search(r"['\"](\d+\.\d+[\.\d]*)['\"]", line)
                        if m:
                            return m.group(1)
            except OSError:
                pass
        return '0.1.0'

    def _generate_pyproject_toml(self, toml_path):
        """Crea un pyproject.toml minimo PEP 621 se non ne esiste uno."""
        version = self._detect_version()

        doc = tomlkit.document()

        build_system = tomlkit.table()
        build_system.add('requires', ['setuptools>=61', 'wheel'])
        build_system.add('build-backend', 'setuptools.backends.legacy:build')
        doc.add('build-system', build_system)
        doc.add(tomlkit.nl())

        project = tomlkit.table()
        project.add('name', self.lib_name)
        project.add('version', version)
        project.add('description', '')
        project.add('dependencies', tomlkit.array())
        doc.add('project', project)
        doc.add(tomlkit.nl())

        find_table = tomlkit.table(is_super_table=True)
        packages_find = tomlkit.table()
        packages_find.add('where', ['.'])
        packages_find.add('include', [f'{self.lib_name}*'])
        find_table.add('packages', tomlkit.table(is_super_table=True))
        find_table['packages'].add('find', packages_find)
        tool = tomlkit.table(is_super_table=True)
        tool.add('setuptools', find_table)
        doc.add('tool', tool)

        with open(toml_path, 'w', encoding='utf-8') as f:
            f.write(tomlkit.dumps(doc))
        print(f'Generated {toml_path}')

    def _write_toml_mapping(self, toml_path, entries, requirements_versioned):
        """Aggiorna [project.dependencies] e [project.optional-dependencies] in pyproject.toml."""
        with open(toml_path, 'r', encoding='utf-8') as f:
            doc = tomlkit.load(f)

        if 'project' not in doc:
            doc.add('project', tomlkit.table())

        # [project.dependencies] — lista flat, equivalente a install_requires
        dep_array = tomlkit.array()
        dep_array.multiline(True)
        for d in sorted(requirements_versioned):
            dep_array.append(d)
        doc['project']['dependencies'] = dep_array

        # [project.optional-dependencies] — dipendenze segmentate per cartella/file
        # PEP 508: il nome di un extra deve iniziare e finire con [A-Za-z0-9].
        # __init__ termina con '_' (es. mylib.__init__) e non è un extra installabile utile: va saltato.
        opt_table = tomlkit.table()
        for e in entries:
            if e['path'].split('.')[-1] == '__init__':
                continue
            _, _, versioned, _ = self.clean_from_python_packages(e['req'])
            if not versioned:
                continue
            arr = tomlkit.array()
            arr.multiline(True)
            for v in sorted(versioned):
                arr.append(v)
            # tomlkit gestisce automaticamente le quoted keys con i punti
            opt_table.add(tomlkit.items.SingleKey(e['path']), arr)
        doc['project']['optional-dependencies'] = opt_table

        with open(toml_path, 'w', encoding='utf-8') as f:
            f.write(tomlkit.dumps(doc))

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

    def _expand_private_lib_dependencies(self, used_private_libs, used_private_paths=None):
        """Per ogni libreria privata effettivamente importata, legge le sue Requires-Dist
        (i requirements dichiarati al momento dell'installazione pip) e restituisce un set
        di nomi di pacchetti da aggiungere ai requirements del progetto.

        Selezione delle dipendenze:
        - Le dipendenze "base" (senza environment marker `extra ==`) sono sempre incluse.
        - Le dipendenze in extras (`; extra == "<nome>"`) sono incluse solo se `<nome>`
          compare in `used_private_paths`. Cosi una libreria privata mappata con DependiPy
          stesso (che mette tutte le dipendenze in `extras_require`, una per ramo del codice)
          contribuisce solo le dipendenze dei rami davvero importati - lo stesso modello di
          `pip install Tages[Tages.preprocess.X]`.
        - Espande ricorsivamente le sotto-dipendenze a loro volta private (BFS con visited),
          cosi una catena di librerie private viene "appiattita" sui pacchetti pubblici.
        - Se una private e' in config ma non installata, emette un warning e prosegue.
        """
        if used_private_paths is None:
            used_private_paths = set()
        expanded = set()
        visited = set()
        pending = list(used_private_libs)
        while pending:
            plib = pending.pop()
            if plib in visited:
                continue
            visited.add(plib)
            try:
                requires = metadata.requires(plib) or []
            except metadata.PackageNotFoundError:
                warnings.warn(
                    f"Private library '{plib}' is configured in private_lib and imported by "
                    f"the code, but is NOT installed in the current environment. Cannot expand "
                    f"its Requires-Dist for --inline_private. Install it and re-run.",
                    stacklevel=2,
                )
                continue
            for req_str in requires:
                extra_name = self._parse_extra_name(req_str)
                # filtro per gli extras: includo solo se il nome dell'extra coincide con un
                # ramo realmente importato. Per le dipendenze "base" (extra_name is None) procedo.
                if extra_name is not None and extra_name not in used_private_paths:
                    continue
                dep_name = self._parse_dep_name(req_str)
                if not dep_name:
                    continue
                if dep_name in self.librerie_private:
                    # la dipendenza e' a sua volta privata: l'appiattiamo seguendone le Requires-Dist
                    pending.append(dep_name)
                else:
                    expanded.add(dep_name)
        return expanded

    @staticmethod
    def _parse_extra_name(req_str):
        """Restituisce il nome dell'extra se la Requires-Dist e' condizionata da `extra == "..."`,
        altrimenti None. Es: 'pandas; extra == "Tages.preprocess.X"' -> 'Tages.preprocess.X'."""
        if ';' not in req_str:
            return None
        marker = req_str.split(';', 1)[1]
        m = re.search(r'extra\s*==\s*["\']([^"\']+)["\']', marker)
        return m.group(1) if m else None

    @staticmethod
    def _parse_dep_name(req_str):
        """Estrae il nome del pacchetto da una stringa Requires-Dist (es. 'pandas (>=1.5)' -> 'pandas')."""
        m = _PKG_NAME_RE.match(req_str)
        return m.group(1) if m else None
