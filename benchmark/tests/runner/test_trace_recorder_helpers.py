from benchmark.runner.trace_recorder import ArtifactWriteResult


def test_artifact_write_result_is_hashable_with_immutable_warnings() -> None:
    result = ArtifactWriteResult(
        path="/tmp/case_1.jsonl",
        state="write_error",
        warnings=("trace_jsonl_write_error: boom",),
    )

    assert isinstance(hash(result), int)
