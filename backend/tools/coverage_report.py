#!/usr/bin/env python3
"""Отчёт о покрытии строк без внешних зависимостей (нужен Python 3.12+, sys.monitoring).

Запускает pytest в этом же процессе и считает, какие строки прикладного кода (папка app/)
были выполнены. Тесты, зависимости и сторонний код в отчёт не попадают.
Строки и блоки с комментарием `# pragma: no cover` не учитываются (как в coverage.py).

Примеры:
    python tools/coverage_report.py
    python tools/coverage_report.py --fail-under 80 --html coverage-report --text coverage.txt
    python tools/coverage_report.py -- -k leave        # свои аргументы для pytest

Эквивалент на coverage.py: python -m pytest --cov=app --cov-report=term-missing
"""
import argparse
import html
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)


def executable_lines(path):
    """Номера строк, на которых есть исполняемый код, и строки, исключённые pragma."""
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    lines = source.splitlines()

    excluded = set()
    for index, text in enumerate(lines, start=1):
        if "pragma: no cover" in text:
            excluded.add(index)
            if text.split("#")[0].rstrip().endswith(":"):
                indent = len(text) - len(text.lstrip())
                for follow in range(index + 1, len(lines) + 1):
                    body = lines[follow - 1]
                    if body.strip() and len(body) - len(body.lstrip()) <= indent:
                        break
                    excluded.add(follow)

    found = set()

    def walk(code):
        for _start, _end, line in code.co_lines():
            if line:
                found.add(line)
        for const in code.co_consts:
            if hasattr(const, "co_lines"):
                walk(const)

    walk(compile(source, path, "exec"))
    return sorted(found - excluded), lines


def ranges(numbers):
    """[1,2,3,7,9,10] -> '1-3, 7, 9-10'."""
    parts, start, prev = [], None, None
    for number in numbers:
        if start is None:
            start = prev = number
        elif number == prev + 1:
            prev = number
        else:
            parts.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = number
    if start is not None:
        parts.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(parts)


def measure(source_dir, pytest_args):
    import pytest

    monitoring = sys.monitoring
    tool = monitoring.COVERAGE_ID
    monitoring.use_tool_id(tool, "ai-buddy-coverage")
    hits = {}
    prefix = source_dir + os.sep

    def on_line(code, line):
        name = os.path.normpath(code.co_filename)
        if name.startswith(prefix):
            hits.setdefault(name, set()).add(line)
        return monitoring.DISABLE  # каждую строку достаточно увидеть один раз

    monitoring.register_callback(tool, monitoring.events.LINE, on_line)
    monitoring.set_events(tool, monitoring.events.LINE)
    try:
        exit_code = pytest.main(pytest_args)
    finally:
        monitoring.set_events(tool, 0)
        monitoring.free_tool_id(tool)
    return exit_code, hits


def build_rows(source_dir, hits):
    rows = []
    for name in sorted(os.listdir(source_dir)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(source_dir, name)
        executable, lines = executable_lines(path)
        covered = hits.get(path, set()) & set(executable)
        missing = [n for n in executable if n not in covered]
        rows.append({"name": name, "path": path, "lines": lines, "executable": executable,
                     "covered": covered, "missing": missing})
    return rows


def text_report(rows):
    out = [f"{'Файл':<18}{'Строк':>7}{'Пропущено':>11}{'Покрытие':>10}  Непокрытые строки"]
    total = miss = 0
    for row in rows:
        n, m = len(row["executable"]), len(row["missing"])
        total += n
        miss += m
        percent = 100.0 if n == 0 else 100.0 * (n - m) / n
        out.append(f"app/{row['name']:<14}{n:>7}{m:>11}{percent:>9.0f}%  {ranges(row['missing'])}")
    percent = 100.0 if total == 0 else 100.0 * (total - miss) / total
    out.append("-" * 70)
    out.append(f"{'ИТОГО':<18}{total:>7}{miss:>11}{percent:>9.1f}%")
    return "\n".join(out), percent


def html_report(rows, percent, directory):
    os.makedirs(directory, exist_ok=True)
    style = ("body{font-family:system-ui,sans-serif;margin:24px;max-width:1000px}"
             "table{border-collapse:collapse;width:100%}td,th{padding:6px 10px;"
             "border-bottom:1px solid #ddd;text-align:left}pre{font-size:13px;line-height:1.4}"
             ".hit{background:#d7f5df}.miss{background:#ffd9de}.skip{color:#888}")
    index = [f"<!doctype html><meta charset=utf-8><title>Покрытие</title><style>{style}</style>",
             f"<h1>Покрытие строк: {percent:.1f}%</h1><table>"
             "<tr><th>Файл<th>Строк<th>Пропущено<th>Покрытие"]
    for row in rows:
        n, m = len(row["executable"]), len(row["missing"])
        value = 100.0 if n == 0 else 100.0 * (n - m) / n
        index.append(f"<tr><td><a href='{row['name']}.html'>app/{row['name']}</a>"
                     f"<td>{n}<td>{m}<td>{value:.0f}%")
        body = [f"<!doctype html><meta charset=utf-8><style>{style}</style>"
                f"<h2>app/{row['name']}</h2><a href='index.html'>← к списку</a><pre>"]
        executable, covered = set(row["executable"]), row["covered"]
        for number, text in enumerate(row["lines"], start=1):
            cls = "skip"
            if number in executable:
                cls = "hit" if number in covered else "miss"
            body.append(f"<span class='{cls}'>{number:4d}  {html.escape(text)}</span>")
        body.append("</pre>")
        with open(os.path.join(directory, row["name"] + ".html"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(body))
    index.append("</table>")
    with open(os.path.join(directory, "index.html"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(index))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=os.path.join(BACKEND, "app"))
    parser.add_argument("--fail-under", type=float, default=80.0)
    parser.add_argument("--html", help="папка для HTML-отчёта")
    parser.add_argument("--text", help="файл для текстового отчёта")
    args, pytest_args = parser.parse_known_args()
    pytest_args = [a for a in pytest_args if a != "--"] or [os.path.join(BACKEND, "tests")]

    source_dir = os.path.abspath(args.source)
    sys.path.insert(0, BACKEND)
    exit_code, hits = measure(source_dir, ["-q", "-p", "no:cacheprovider"] + pytest_args)
    rows = build_rows(source_dir, hits)
    report, percent = text_report(rows)
    print("\n" + report)

    if args.text:
        os.makedirs(os.path.dirname(os.path.abspath(args.text)), exist_ok=True)
        with open(args.text, "w", encoding="utf-8") as handle:
            handle.write(report + "\n")
    if args.html:
        html_report(rows, percent, args.html)
        print(f"HTML-отчёт: {args.html}/index.html")

    if exit_code != 0:
        print("Тесты не прошли.")
        return int(exit_code)
    if percent < args.fail_under:
        print(f"Покрытие {percent:.1f}% ниже порога {args.fail_under}%.")
        return 2
    print(f"Покрытие {percent:.1f}% (порог {args.fail_under}%): OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
