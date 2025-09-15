def test_union_isinstance_works():
    e = RuntimeError("test")
    assert isinstance(e, RuntimeError | ValueError), (
        "Your Python runtime does not support `isinstance(obj, A | B)` — please use tuples `(A, B)` instead."
    )
