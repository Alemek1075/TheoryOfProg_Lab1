# Команда sipl

Після `pip install -e .` з'являється команда `sipl`. Те саме робить `python -m sipl`.

    sipl check FILE [--json]
    sipl parse FILE [--json]
    sipl run   FILE [NAME=NUMBER ...] [--step-limit N] [--json]
    sipl trace FILE [NAME=NUMBER ...] [--step-limit N] [--json]

`FILE` це шлях до програми. Якщо написати `-`, програма читається зі stdin.
Файл має бути в UTF-8.

`NAME=NUMBER` задає початкове значення змінної, наприклад `X=2 Y=-3`.
Змінна, якій нічого не присвоєно і яку не задано тут, значення не має.
Читання такої змінної це помилка виконання.

`--step-limit N` зупиняє програму після N кроків. За замовчуванням 100000.
Крок це одне присвоювання, один skip або одна перевірка умови if чи while.

## Що роблять команди

`check` перевіряє синтаксис і друкує `ok`.

`parse` друкує AST:

    $ sipl parse examples/valid/max.sipl
    Program
      If
        Compare >
          Var X
          Var Y
        Assign
          Var R
          Var X
        Assign
          Var R
          Var Y

`run` виконує програму і друкує кінцевий стан:

    $ sipl run examples/valid/power.sipl X=2 Y=10
    R = 1024
    X = 2
    Y = 0

`trace` виконує програму і друкує кожен крок: номер кроку, рядок:колонка,
текст оператора чи умови, і що сталося.

    $ sipl trace examples/valid/gcd.sipl M=12 N=18
        1  2:9     not M = N                true
        2  3:8     M > N                    false
        3  3:35    N := N - M               N: 18 -> 6
        4  2:9     not M = N                true
        5  3:8     M > N                    true
        6  3:19    M := M - N               M: 12 -> 6
        7  2:9     not M = N                false
        8  4:3     R := M                   R: - -> 6
    finished in 8 steps
    M = 6
    N = 6
    R = 6

Помилки без `--json` друкуються в stderr разом із рядком програми:

    $ sipl check examples/invalid/equals.sipl
    examples/invalid/equals.sipl:2:5: error: unexpected '=', expected ':='
        R = 1
          ^

## Коди завершення

| Код | Що означає |
|---|---|
| 0 | все добре |
| 1 | синтаксична помилка в програмі |
| 2 | неправильні аргументи або файл не читається |
| 3 | помилка виконання: змінна без значення або перевищено ліміт кроків |

## JSON

З `--json` результат це один рядок JSON у stdout, і в разі помилки теж.
Виняток один: неправильні аргументи командного рядка (код 2), тоді в stderr
іде звичайний текст з підказкою.

У кожній відповіді є поле `ok`. Якщо `ok` дорівнює false, є поле `error`:

    {"kind": "syntax_error", "message": "unexpected '=', expected ':='", "span": {...}}

`kind` буває таким:

| kind | Код завершення |
|---|---|
| syntax_error | 1 |
| file_error | 2 |
| too_deep | 2 |
| undefined_variable | 3 |
| step_limit | 3 |
| runtime_error | 3 |

`too_deep` буває тільки в `parse`: дерево програми на тисячі операторів підряд
занадто глибоке, щоб його надрукувати. Виконується така програма нормально.

`span` це місце в тексті програми. Рядки й колонки рахуються з 1, `start` і `end`
це зсуви в символах від початку файлу, `end` не включається. Там, де місця немає
(наприклад, файл не знайдено), `span` дорівнює null.

    {"line": 2, "column": 5, "end_line": 2, "end_column": 6, "start": 10, "end": 11}

### check

    {"ok": true}

### parse

    {"ok": true, "ast": {"type": "Program", "body": {...}, "span": {...}}}

Кожен вузол має `type` і `span`. Решта полів залежить від типу:

| type | Поля |
|---|---|
| Program | body |
| Assign | target (вузол Var), value |
| Seq | first, second |
| If | cond, then, orelse |
| While | cond, body |
| Block | body |
| Skip | |
| Num | value |
| Var | name |
| BinOp | op (`+`, `-`, `*`), left, right |
| Compare | op (`=`, `>`), left, right |
| Or | left, right |
| Not | cond |

### run

    {"ok": true, "state": {"R": 8, "X": 2, "Y": 0}, "steps": 11}

Якщо сталася помилка виконання, `state` і `steps` теж є. Це стан на момент помилки.

    {"ok": false, "error": {...}, "state": {"R": 1, "X": 2}, "steps": 2}

Змінні в `state` відсортовані за іменем.

### trace

    {"ok": true, "events": [...]}

Якщо сталася помилка виконання, `ok` дорівнює false, є поле `error`,
а останньою подією йде `failed`.

Події йдуть у тому порядку, в якому відбувалися. У кожної є `event` і `step`
(номер кроку, з 1).

| event | Поля | Коли |
|---|---|---|
| before_statement | statement, span | перед оператором |
| after_statement | statement, span | оператор закінчився |
| variable_changed | name, old, new, span | присвоювання; old дорівнює null, якщо значення не було |
| condition_checked | statement, result, span | перевірено умову if чи while; span це місце умови |
| finished | state | програма завершилась |
| failed | error, message, span | помилка виконання; error це той самий kind |

`statement` буває `assign`, `skip`, `if`, `while`, `block`.
Для `S1; S2` окремих подій немає.

`variable_changed` надсилається на кожне присвоювання, навіть коли нове значення
таке саме, як старе.

Для `while` події `before_statement` і `after_statement` надсилаються по одному разу
на весь цикл, а `condition_checked` на кожну перевірку.
