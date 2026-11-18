# Changelog

Версії за SemVer.

## 0.2.0 - 2026-11-18

Додано:
- дебагер через Debug Adapter Protocol, запуск `python -m sipl.dap`
- точки зупину по рядках, прив'язані до span операторів в AST; точка на порожньому рядку переїжджає на наступний оператор
- continue, step, stop on entry, перегляд змінних, evaluate виразів і умов
- зупинка з помилкою, якщо змінна без значення або перевищено step limit
- розширення VS Code в папці vscode: підсвітка .sipl, F5 запускає дебагер
- публікація в PyPI з GitHub Actions

## 0.1.0 - 2026-11-17

Перша версія.
- граматика SIPL (Lark), парсер, AST з SourceSpan
- покроковий інтерпретатор, події виконання і trace
- CLI: check, parse, run, trace, вивід у JSON
- CI на Linux і Windows, Python 3.10 і 3.13
