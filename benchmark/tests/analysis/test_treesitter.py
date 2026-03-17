from benchmark.analysis.treesitter import extract_signature, get_parser


class TestGetParser:
    def test_returns_parser(self) -> None:
        parser = get_parser()
        assert parser is not None

    def test_returns_same_instance(self) -> None:
        parser1 = get_parser()
        parser2 = get_parser()
        assert parser1 is parser2


class TestExtractSignature:
    def test_simple_function(self) -> None:
        code = b"def foo(x: int) -> str:\n    return str(x)"
        parser = get_parser()
        tree = parser.parse(code)
        func_node = tree.root_node.children[0]
        assert func_node.type == "function_definition"
        sig = extract_signature(func_node, code)
        assert sig == "def foo(x: int) -> str"

    def test_function_no_return_type(self) -> None:
        code = b"def bar(a, b):\n    pass"
        parser = get_parser()
        tree = parser.parse(code)
        func_node = tree.root_node.children[0]
        sig = extract_signature(func_node, code)
        assert sig == "def bar(a, b)"

    def test_multiline_signature(self) -> None:
        code = b"def baz(\n    a: int,\n    b: str,\n) -> None:\n    pass"
        parser = get_parser()
        tree = parser.parse(code)
        func_node = tree.root_node.children[0]
        sig = extract_signature(func_node, code)
        assert "def baz" in sig
        assert "a: int" in sig
        assert "b: str" in sig
        assert "->" in sig
