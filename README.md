# SIPL

![CI](https://github.com/Alemek1075/TheoryOfProg_Lab1/actions/workflows/ci.yml/badge.svg)

Курсовий проєкт з теорії програмування, Базилевич Олексій, ТТП-32.

Тут інтерпретатор мови SIPL з лекцій і дебагер до нього, на Python.

Що взяв:
- CORE-01 граматика (0.5)
- CORE-02 парсер і AST (1.5)
- CORE-03 інтерпретатор (2.0)
- CORE-04 trace (1.0)
- CORE-05 CLI (1.0)
- IDE-03 дебагер (2.5)
- REL-01 CI (0.5)
- REL-02 релізи (0.5)
- REL-03 PyPI (0.5)

Разом 10 балів.

Граматика в src/sipl/grammar/sipl.lark, приклади програм в examples, опис CLI в docs/cli.md, зміни по версіях в CHANGELOG.md.

Запуск: `pip install sipl-interpreter` (або `pip install -e .` з репозиторію), потім `sipl run examples/valid/power.sipl X=2 Y=10`.

Дебагер: відкрити репозиторій у VS Code, F5 (конфіг "Run SIPL extension"). Відкриється друге вікно з папкою examples, там відкрити будь-який .sipl, поставити точку зупину і ще раз F5. Можна і без цього, поставивши .vsix з релізу.
