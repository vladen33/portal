r"""Рендер шаблонов deploy: подставляет значения вместо @KEY@.

Скрипт не зависит от Django и запускается системным python3.
Значения передаются переменными окружения с префиксом ``T_``:
так спецсимволы (``&``, ``|``, ``\``, ``$``) не ломают подстановку,
а секреты не попадают в список аргументов процесса.
"""

import os
import re
import sys

# Плейсхолдеры вида @APP_DIR@, @DOMAIN@, @SECRET_KEY@.
PLACEHOLDER = re.compile(r'@[A-Z][A-Z0-9_]*@')


def render(template_path, output_path):
    """Читает шаблон, подставляет значения и пишет результат.

    Если в результате остались неподставленные плейсхолдеры,
    скрипт завершается с ошибкой: лучше упасть на установке,
    чем получить конфиг с литералом @DOMAIN@.
    """
    with open(template_path, encoding='utf-8') as source:
        text = source.read()

    for name, value in os.environ.items():
        if name.startswith('T_'):
            text = text.replace(f'@{name[2:]}@', value)

    missing = sorted(set(PLACEHOLDER.findall(text)))
    if missing:
        raise SystemExit(
            'Не подставлены значения: ' + ', '.join(missing),
        )

    with open(output_path, 'w', encoding='utf-8') as target:
        target.write(text)


def main(argv):
    """Точка входа: ``render.py TEMPLATE OUTPUT``."""
    if len(argv) != 3:
        print('usage: render.py TEMPLATE OUTPUT', file=sys.stderr)
        return 2
    render(argv[1], argv[2])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
