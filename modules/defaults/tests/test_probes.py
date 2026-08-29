from modules.defaults.backend.probes import one_line


def result(stdout="", exit_code=0, timed_out=False, stderr=""):
    return {"stdout": stdout, "exitCode": exit_code, "timedOut": timed_out, "stderr": stderr}


def test_one_line_accepts_empty_and_single_line():
    assert one_line(result("zen\n")) == ("zen", "")
    assert one_line(result("")) == ("", "")


def test_one_line_rejects_multiline_timeout_and_failure():
    assert one_line(result("zen\nextra\n"))[1] == "malformed_output"
    assert one_line(result(timed_out=True))[1] == "timeout"
    assert one_line(result(exit_code=1, stderr="failed\n"))[1] == "failed"
