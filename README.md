# SIPL

![CI](https://github.com/Alemek1075/TheoryOfProg_Lab1/actions/workflows/ci.yml/badge.svg)

Курсовий проєкт з теорії програмування. Інтерпретатор SIPL і дебагер до нього.

Завдання:
- CORE-01 граматика (0.5)
- CORE-02 парсер і AST (1.5)
- CORE-03 інтерпретатор (2.0)
- CORE-04 trace (1.0)
- CORE-05 CLI (1.0)
- IDE-03 дебагер (2.5)
- REL-01 CI (0.5)
- REL-02 релізи (0.5)
- REL-03 PyPI (0.5)

Всього 10 балів.

Як запустити (потрібен Python 3.10 або новіший):

    pip install -e ".[dev]"
    sipl run examples/valid/power.sipl X=2 Y=10
    pytest

Команди:

    sipl check файл.sipl            перевірити синтаксис
    sipl parse файл.sipl            показати AST
    sipl run файл.sipl X=2 Y=3      виконати, X і Y це початкові значення
    sipl trace файл.sipl X=2 Y=3    виконати і показати кожен крок

До кожної можна дописати --json. Формат JSON і коди завершення є в docs/cli.md.

Приклади програм лежать в examples: valid це правильні, invalid це з помилками.
