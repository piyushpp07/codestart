from pathlib import Path

from claude_code.context.indexers.code_parser import get_source_files, parse_file


def test_parse_python_file_extracts_function_metadata(tmp_path: Path) -> None:
    source = tmp_path / "example.py"
    source.write_text("def greet(name):\n    return f'Hello {name}'\n", encoding="utf-8")

    chunks = parse_file(str(source))

    assert len(chunks) == 1
    assert chunks[0].name == "greet"
    assert chunks[0].type == "function"
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 2


def test_get_source_files_excludes_virtual_environments(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    venv_file = tmp_path / ".venv" / "lib" / "ignored.py"
    venv_file.parent.mkdir(parents=True)
    venv_file.write_text("x = 2\n", encoding="utf-8")

    files = get_source_files(str(tmp_path))

    assert str(tmp_path / "app.py") in files
    assert str(venv_file) not in files


def test_parse_react_and_node_related_text_files(tmp_path: Path) -> None:
    module = tmp_path / "server.mjs"
    module.write_text("export const server = true;\n", encoding="utf-8")
    component = tmp_path / "App.vue"
    component.write_text("<template><main>Hello</main></template>\n", encoding="utf-8")
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM node:22\n", encoding="utf-8")

    assert parse_file(str(module))[0].type == "block"
    assert parse_file(str(component))[0].content.startswith("<template>")
    assert parse_file(str(dockerfile))[0].content == "FROM node:22"
