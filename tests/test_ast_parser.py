"""
Tests for AST Parser — verify extraction of functions, classes, imports, mutations.
"""

from app.core.ast_parser import parse_python


def test_extracts_functions(sample_python_code):
    result = parse_python(sample_python_code, "test.py")
    func_names = {f.name for f in result.functions}
    assert "process_file" in func_names
    assert "execute_code" in func_names
    assert "fetch_data" in func_names
    assert "update_shared" in func_names
    assert "retry_api" in func_names


def test_extracts_async_functions(sample_python_code):
    result = parse_python(sample_python_code, "test.py")
    async_funcs = [f for f in result.functions if f.is_async]
    async_names = {f.name for f in async_funcs}
    assert "fetch_data" in async_names
    assert "update_shared" in async_names
    assert "sync_shared" in async_names


def test_extracts_imports(sample_python_code):
    result = parse_python(sample_python_code, "test.py")
    import_modules = {i.module for i in result.imports}
    assert "os" in import_modules
    assert "time" in import_modules
    assert "requests" in import_modules


def test_extracts_module_level_mutations(sample_python_code):
    result = parse_python(sample_python_code, "test.py")
    mutation_names = {m.name for m in result.variable_mutations}
    assert "shared_data" in mutation_names
    assert "config_cache" in mutation_names


def test_detects_mutable_types(sample_python_code):
    result = parse_python(sample_python_code, "test.py")
    type_map = {m.name: m.target_type for m in result.variable_mutations}
    assert type_map.get("shared_data") == "list"
    assert type_map.get("config_cache") == "dict"


def test_extracts_function_calls(sample_python_code):
    result = parse_python(sample_python_code, "test.py")
    process_file = next(f for f in result.functions if f.name == "process_file")
    assert "open" in process_file.calls


def test_handles_syntax_error():
    result = parse_python("def broken(:\n  pass", "broken.py")
    assert len(result.parse_errors) > 0
    assert result.file_path == "broken.py"


def test_clean_code_parsing(clean_python_code):
    result = parse_python(clean_python_code, "clean.py")
    assert len(result.functions) == 2
    add_func = next(f for f in result.functions if f.name == "add")
    assert add_func.return_annotation == "int"
    assert len(add_func.parameters) == 2


def test_async_boundaries(sample_python_code):
    result = parse_python(sample_python_code, "test.py")
    assert any(b.type == "async_def" for b in result.async_boundaries)
