# DependiPy
gli script in questa repository servono per mappare le dipendenze di una libreria in modo da poterle selezionare
in modo modulare quando la libreria mappata viene installata, o in alternativa crea il file requirements.txt con
le dimendenze esatte installate sul sistema da cui si sta lanciando lo script.

## files
sono presenti 2 files:
- librarian.py, che contiene lo script main
- archive.py, che contiene una classe usata da librarian.py

## execution
per usare le funzionalita di mapping venogno richiesti 1 parametro obligatorio e 3 opzionali:
- obligatori
  - **path**, percorso fino alla cartella della libreria o script
- opzionali:
  - **mode**, da scegliere tra 2 modalita, se non viene compilato lo script prova a capire in autonomia quale sia la modalita corretta:
    - *lib*, se si vuole mappare le dipendenze di una libreria
    - *script*, se si vuole mappare le dipendenze di una script con le librerie custom
  - **config**, vuole il percorso ad un file di config con alcune info aggiuntive su enventuali modifiche dal funzionamento standard. Il config deve essere un file json.
  - **docs_only**, se attivata questa modalita non genera i file dei requirements o setup.py ma solo i file per la documentazione

Se si sta lavorando in lib la cartella indicata nel path è la cartella della libreria, non quella che contiene il setup.py ma quella un livello piu interno a setup.py.
Se si sta lavorando in script la cartella indicata è quella che contiene lo/gli script.

Librarian è in grado di mappare sia script dentro cartelle con nessun limite sui livelli di profondita.
Libraria è in grado di mappare le cross dipendenze dentro la libreria indicata.

l'esecuzione va invocata come di seguito:
```bash
DependiPy -p <path> -m <mode> -c <config.json>
```

Il file config deve avere la seguente struttura:
```json
{
  "private_lib": ["lib1", "lib2"],
  "replace_lib": {
    "dateutil": ["python-dateutil"],
    "sklearn": ["scikit-learn"],
    "azure":
    ["azure-common",
      "azure-core",
      "azure-identity",
      "azure-mgmt-consumption",
      "azure-mgmt-core",
      "azure-mgmt-costmanagement"
    ]},
  "exclude_lib": ["tensorflow", "setuptools"],
  "exclude_folder": ["tests", "__pycache__", "discontinue", "git", "idea"],
  "force_version": {"pandas": "pandas==1.1.1", "numpy": "numpy"}
}
```
- **privat_lib**: sono le librerie private usate che non sono presenti su PyPi e che quindi non devono essere listate in un file di requirements, non potendo essere installate in automatico
- **replace_lib**: sono le parole che devono essere sostituite nella ricerca delle librerie, dato che alcune librerie usano nomi diversi negli import dalle release su PyPi
- **exclude_lib**: librerie che sono presenti nei file ma che non si vuole che vengano riportate
- **exclude_folder**: cartelle che non devono essere considerate durante lo scan delle dipendenze
- **force_version** sono le librerie di cui si vuole forzare una versione, viene usato un formato a dizionario dove la chiave e' la libreria identificata e il valore e' la stringa che si vuole usare dei requirements, si puo mettere una versione specifica o inserire solo il nome per non segnalare nessuna versione

**Le librerie inserite nel requirements.txt sono sempre e solo quelle che devono essere installate, per cui non verranno mai riportate le dipendenze native di Python**

## lib/setup.py
Se si sta lavorando in modalita lib, libraria produce un file alla fine della mappatura.
Se il setup.py ha la forma seguente:
```python
from setuptools import find_packages, setup

version = '1.0'

# version go
sqlalchemy = 'sqlalchemy'
pyodbc = 'pyodbc'
argparse = 'argparse'
urllib3 = 'urllib3~=1.26.9'
tqdm = 'tqdm~=4.64.0'
requests = 'requests'
pandas = 'pandas~=1.4.2'
tabulate = 'tabulate~=0.8.9'
# version end

# start
requires_dict = {
'utilities': [pandas, requests, argparse, tabulate, tqdm, sqlalchemy, urllib3],
'utilities.args': [argparse],
'utilities.args.parser': [argparse],
'utilities.decorators': [],
'utilities.dictionary': [],
'utilities.io': [pandas, requests, tabulate, tqdm, sqlalchemy, urllib3],
'utilities.io.analytics_job_util': [pandas, requests, tabulate, tqdm, urllib3],
'utilities.io.api': [tqdm, requests, urllib3],
'utilities.io.database': [sqlalchemy],
'utilities.io.exceptions.api': [],
'utilities.io.pickle': [],
'utilities.logs': [argparse],
'utilities.logs.logger': [argparse],
'utilities.notification': [requests],
'utilities.notification.telegram': [requests],
}
# stop

setup(
    name='utilities',
    version=version,
    packages=find_packages(include=['utilities']),
    license='',
    author='John Do',
    author_email='',
    description='',
    url="https://github.com/rep.git",
    extras_require=requires_dict,
    install_requires=[],
)
```
Sono necessarie le seguenti chiavi nel setup.py: **# start**, uno **# stop**, uno **# version go** e uno **# version end**.
Librarian andra a scrivere la mappatura direttamente nel setup.py.

## script/k8s_config.json
Se si sta lavorando in modalita script, librarian cerchera tutte le dipendenze con le libreria custom indicate nel codice.
Per modificare o aggiungere tali librerie fare riferimento al config con la forma:
```json
"private_lib": ["Tages", "utilities"]
```
nell'esempio qui indicato vengono cercate le dipendenze con le librerie **Tages** e **utilities**.

Librarian mappera le connessioni con tali librerie e produrra un risultato sul terminale nella forma:
```powershell
[Tages.utilities.generic,Tages.preprocess.time_series.data_preparation,Tages.preprocess.data_preparation]

[utilities.args.parser,utilities.io.analytics_job_util]
```
una riga per libreria indicata.

Queste righe vanno copiate e incollate in fare di installazione dello script per installare le sole dipendenze delle librerie necessarie per il funzionamento dello scritp

## escludere alcune librerie o cartelle specifiche
Per escludere cartelle specifiche dalla mappatura in modalita lib è possibile aggiungere nomi di cartelle alla lista:
```json
"exclude_folder": ['tests', '__pycache__', 'discontinue']
```
Mentre se si vuole escludere alcune librerie dal mappaggio:
```json
"exclude_lib": ['os', 'string', 'inspect', 'logging', 'sys', 'abc', 'statistics', 'pickle', 'collections', 'functools',
                 'json', 'itertools', 'warnings', 'typing', 'calendar', 'datetime', 'hashlib', 'time', 'random']
```

## come usare i moduli su pip
Quando si deve pip installare una libreria per usarla in relazione ad uno script è sempre possibile indicare delle specifiche sotto
categorie di dipendenze con i moduli di pip (se precedentemenete mappati).

Un esempio di installazione di **Tages** con le dipendenze necessarie per uno specifico script al suo interno puo essere scritto come:
```bash
pip install -e ./AI_lib[Tages.preprocess.time_series.data_preparation]
```

La mappatura fatta permette di indicare i singoli file o cartelle, facendo cosi verranno incluse le sole dipendenze
necessarie richieste dagli script selezionati.

E' possibile concatenare piu moduli se si sta usando piu parti della libreria mappata
```bash
pip install -e ./utilities[utilities.args.parser,utilities.io.analytics_job_util]
```

# Documentation

E' possibile generare automaticamente la documentazione del codice, assieme a documentazione scritta a mano, su un sito autogenerato da github (per le sole repository publiche).
**Requirements_mapper** permette di generare i file che servono per autodocumentare il codice tramite la documentazione riportata nei docsting.

## guida all'uso di mkdocs

i passi da fare sono i seguenti:
1. installare le seguenti librerie
    ```bash
    pip install mkdocs
    pip install "mkdocstrings[python]"
    pip install mkdocs-material
    ```
2. con il seguente comando vengono create le cartelle necessarie alla formazione della documentazione, lanciarlo dentro alla cartella del codice (se si tratta di una libreria, farlo allo stesso livello di setup.py)
    ```bash
    mkdocs new .
    ```
3. viene quindi creata una cartella **docs** ed un file **mkdocs.yaml**. Il file **mkdocs.yaml** deve essere composta da un testo simile al seguente:
    ```yaml
    site_name: titolo sito
    site_description: description del sito
    site_url: url di riferimento
    
    theme:
      name: material
      features:
        - search.suggest
        - search.highlight
        - content.tabs.link
        - content.tooltips
    #    - navigation.tabs
    #    - navigation.tabs.sticky
        - navigation.sections
    #    - navigation.path
        - navigation.top
        - navigation.expand
        - content.code.annotate
        - content.code.copy
        - content.code.select
    #    - toc.integrate
        - toc.follow
        - header.autohide
    
      language: en
      palette:
        - scheme: default
          toggle:
            icon: material/toggle-switch-off-outline
            name: Switch to dark mode
          primary: orange
          accent: purple
        - scheme: slate
          toggle:
            icon: material/toggle-switch
            name: Switch to light mode
          primary: orange
          accent: lime
    
    repo_name: name repository github
    repo_url: url repository github
    
    plugins:
      - mkdocstrings
      - search
    
    markdown_extensions:
      - pymdownx.highlight:
          anchor_linenums: true
      - pymdownx.inlinehilite
      - pymdownx.snippets
      - admonition
      - pymdownx.arithmatex:
          generic: true
      - footnotes
      - pymdownx.details
      - pymdownx.superfences
      - pymdownx.mark
      - attr_list
    
    nav:
      - index.md
      - Installation: installation.md
      - User Guide: user_guide.md
      - Developer Guide: dev_guide.md
      - XA information: info.md
    
    copyright:
      mit
    ```
4. nella cartella docs devono essere messi i testi che si vogliono far comparire nella documentazione online, sotto forma di file markdown
5. nella sezione **nav** dello yaml devono essere inseriti i file aggiunti alla cartella docs
6. a questo punto si deve lanciare **requirements_mapper**, che andra ad aggiungere file e riferimenti al codice per la documentazione
7. per osservare il risultato in una versione demo si puo lanciare il codice
    ```bash
    mkdocs serve
    ```
8. si deve creare una cartella **.github** al cui interno va creata una cartella **workflowa**
9. dentro a **workflows** deve essere aggiunto un file **ci.yml** il cui contenuto e' il seguente:
    ```yaml
    name: ci
    on:
      push:
        branches:
          - master
          - main
    permissions:
      contents: write
    jobs:
      deploy:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v3
          - uses: actions/setup-python@v4
            with:
              python-version: 3.x
          - uses: actions/cache@v2
            with:
              key: ${{ github.ref }}
              path: .cache
          - run: pip install mkdocs-material
          - run: pip install "mkdocstrings[python]"
          - run: pip install pillow cairosvg
          - run: mkdocs gh-deploy --force
    ```
10. si pusha il primo commit
11. si va su github sulla repo e si cerca la sezione **github pages**
    1. si naviga in settings
    2. si naviga in pages
    3. si naviga in source
       1. deploy from branch
    4. branch
       1. gh-pages
       2. root/
12. dal prossimo commit verra generata automaticamente la documentazione
13. **nel caso venissero creati nuovi file di codice si deve sempre rilanciare requirements_mapper per generare i file con i nuovi docstring
