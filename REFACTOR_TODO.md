# Refactor backlog — secondo round

Cose lasciate fuori dal primo giro di refactor (che ha coperto bug di
correttezza, cross-platform e API deprecate). Questi punti sono
miglioramenti di architettura, qualità e ampliamento dello scope: vanno
affrontati separatamente perché impattano l'API pubblica o la struttura
interna in modo non banale.

## Architetturale

- **Eliminare `os.walk` cieco e modificare `dirnames` in place** per non
  scendere nelle cartelle escluse (efficienza su repo grandi).

- **Supportare `pyproject.toml`** oltre a `setup.py`. Lo standard moderno
  PEP 621 ha sostituito `setup.py` per molti progetti nuovi.

## Qualità del codice

- **`add_path` è `@staticmethod` ma viene chiamato sull'istanza** in
  `librarian.py:66`. Coerenza: o tutti static o tutti di istanza.

- **`cleaning` muta la lista in input e la restituisce.** Anche dopo il
  refactor del primo round resta da decidere se restituire una nuova
  lista (preferibile) o mutare quella esistente — uniformare lo stile.

## Configurabilità

- **Filtro `file.startswith('test')` hardcoded** in `read_files`. Renderlo
  configurabile (es: `exclude_files` regex) o limitarlo a `test_*.py` /
  `*_test.py` invece di qualsiasi file che inizia con "test".


## Robustezza

- **Import dinamici** (`importlib.import_module('foo')`) e
  `__import__('foo')` non vengono catturati. Possibile parsing AST per i
  Call su `importlib.import_module`.

- **`__init__.py` con re-export wildcard.** Se `__init__.py` fa
  `from .submodule import *` e altri file importano dal package, le
  dipendenze possono mancare nella mappatura.


## Test

- **Aggiungere test unitari** su `books_extraction`, `cleaning`,
  `cross_mapping`. Sono le funzioni di logica pura più facili da testare
  e più soggette a regressioni.
